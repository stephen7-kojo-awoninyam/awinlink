import asyncio
import json
import os
from datetime import timedelta
from unittest.mock import AsyncMock, patch
from unittest import skipUnless
from uuid import uuid4

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from django.utils import timezone
from redis.exceptions import RedisError
from rest_framework_simplejwt.tokens import AccessToken

from . import classroom_services as services, classroom_signaling as signaling
from .classroom_events import participant_group, session_group
from .models import AttendanceInterval, ClassroomMembership, Enrollment
from .test_classroom_security import ClassroomFixture


SDP = "v=0\r\no=- 1 1 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\na=ice-ufrag:abcd\r\n"
ICE = {"candidate": "candidate:1 1 udp 2122260223 192.0.2.1 54321 typ host", "sdpMid": "0", "sdpMLineIndex": 0}


class ClassroomSignalValidationTests(SimpleTestCase):
    def test_expired_token_cannot_emit_after_a_database_await(self):
        from .consumers import ClassroomConsumer
        consumer = ClassroomConsumer()
        consumer.deadline, consumer.closing = 0, False
        consumer.terminate, consumer.send = AsyncMock(), AsyncMock()
        async_to_sync(consumer.send_json)({"type": "offer"})
        consumer.terminate.assert_awaited_once_with(4401)
        consumer.send.assert_not_awaited()

    def test_sender_expiring_during_recipient_validation_is_not_relayed(self):
        from .consumers import ClassroomConsumer
        import time
        consumer = ClassroomConsumer()
        consumer.session_id, consumer.participant_id = 1, 2
        consumer.connection_id, consumer.channel_name = uuid4(), "target-channel"
        consumer.authorized, consumer.send_json = AsyncMock(return_value=True), AsyncMock()
        event = {"session_id": 1, "recipient_id": 2, "recipient_channel": consumer.channel_name,
            "recipient_connection": str(consumer.connection_id), "sender_id": 3,
            "sender_connection": str(uuid4()), "sender_channel": "sender-channel",
            "sender_deadline": time.time() + 60, "payload": {"type": "offer"}}
        def expires_during_validation(*args):
            event["sender_deadline"] = 0
            return True
        with patch("learning.classroom_signaling.relay_is_current", side_effect=expires_during_validation):
            async_to_sync(consumer.classroom_signal)(event)
        consumer.send_json.assert_not_awaited()

    def test_offer_answer_ice_and_end_of_candidates(self):
        for kind in ["offer", "answer"]:
            signaling.parse_message(json.dumps({"type": kind, "recipient_id": 2, "description": {"type": kind, "sdp": SDP}}))
        for candidate in [ICE, None, {"candidate": ""}]:
            signaling.parse_message(json.dumps({"type": "ice_candidate", "recipient_id": 2, "candidate": candidate}))
        self.assertEqual(signaling.parse_message('{"type":"ping"}'), {"type": "ping"})

    def test_malformed_non_object_duplicate_and_non_finite_json(self):
        for text in ['[]', 'null', '42', '{', '{"type":"ping","type":"offer"}', '{"type":"ping","other":NaN}']:
            with self.subTest(text=text), self.assertRaises((ValueError, TypeError)):
                signaling.parse_message(text)

    def test_identity_room_and_arbitrary_event_injection_are_rejected(self):
        base = {"type": "offer", "recipient_id": 2, "description": {"type": "offer", "sdp": SDP}}
        for field in ["sender_id", "session_id", "channel_name", "room", "sender_participant_id"]:
            with self.assertRaises(ValueError):
                signaling.validate_message({**base, field: 99})
        for kind in ["classroom_control", "call_ended", "end", "admit", None, []]:
            with self.assertRaises(ValueError):
                signaling.validate_message({**base, "type": kind})

    def test_sdp_size_type_structure_and_recipient_are_validated(self):
        base = {"type": "offer", "recipient_id": 2, "description": {"type": "offer", "sdp": SDP}}
        for recipient in [True, None, "2", -1, 0, 2**63]:
            with self.assertRaises(ValueError):
                signaling.validate_message({**base, "recipient_id": recipient})
        for sdp in [None, "audit", SDP + "malformed\n", SDP + "a=\x00bad", "v=0\n" + "s=" + "x" * 32769]:
            with self.assertRaises(ValueError):
                signaling.validate_message({**base, "description": {"type": "offer", "sdp": sdp}})
        with self.assertRaises(ValueError):
            signaling.validate_message({**base, "description": {"type": "answer", "sdp": SDP}})

    def test_ice_shape_limits_addresses_and_media_coordinates(self):
        bad = [{**ICE, "candidate": "bad"}, {**ICE, "candidate": "x" * 4097},
               {**ICE, "candidate": ICE["candidate"] + "\r\na=extra"}, {**ICE, "sdpMLineIndex": True},
               {**ICE, "sdpMLineIndex": -1}, {**ICE, "sdpMid": "\n"}, {**ICE, "sender_id": 99},
               {"candidate": ICE["candidate"]}, {**ICE, "usernameFragment": "\x00"},
               {**ICE, "candidate": ICE["candidate"].replace("192.0.2.1", "https://evil.example")},
               {**ICE, "candidate": ICE["candidate"].replace("54321", "65536")}]
        for candidate in bad:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                signaling.validate_message({"type": "ice_candidate", "recipient_id": 2, "candidate": candidate})
        for address in ["2001:db8::1", "peer-123.local"]:
            signaling.validate_message({"type": "ice_candidate", "recipient_id": 2,
                "candidate": {**ICE, "candidate": ICE["candidate"].replace("192.0.2.1", address)}})


class SocketFixture(ClassroomFixture):
    def setUp(self):
        delivery = patch("notifications.signals.publish_notification")
        delivery.start()
        self.addCleanup(delivery.stop)
        super().setUp()
        self.first_participant = self.admit()
        self.second_participant = self.admit(self.other)
        self.outsider = get_user_model().objects.create_user(username="websocket-outsider")
        self.tokens = {user.pk: str(AccessToken.for_user(user)) for user in [self.learner, self.other, self.host, self.cohost, self.creator, self.admin, self.outsider]}

    def socket(self, user=None, *, session=None, connection=None, headers=None, query=None):
        from config.asgi import application
        session_id = (session or self.session).pk
        connection = connection or uuid4()
        if headers is None:
            headers = [(b"authorization", f"Bearer {self.tokens[user.pk]}".encode())]
        path = f"/ws/learning/sessions/{session_id}/?{query or 'connection_id=' + str(connection)}"
        return WebsocketCommunicator(application, path, headers=headers)

    async def open_socket(self, user, **kwargs):
        socket = self.socket(user, **kwargs)
        self.assertTrue((await socket.connect())[0])
        ready = await socket.receive_json_from()
        self.assertEqual(ready["type"], "connection")
        return socket, ready

    async def drain(self, socket):
        # Presence is asynchronous and independent of peer negotiation.
        while not await socket.receive_nothing(timeout=0.02):
            await socket.receive_output()

    async def next_type(self, socket, kind):
        for _ in range(20):
            result = await socket.receive_json_from(timeout=3)
            if result["type"] == kind:
                return result
        self.fail(f"Did not receive {kind}")

    async def close_code(self, socket):
        for _ in range(128):
            output = await socket.receive_output(timeout=3)
            if output["type"] == "websocket.close":
                return output["code"]
        self.fail("Socket did not close")

    def offer(self, recipient):
        return {"type": "offer", "recipient_id": recipient, "description": {"type": "offer", "sdp": SDP}}


@override_settings(ALLOWED_HOSTS=["testserver"], CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class ClassroomSocketSecurityTests(SocketFixture, TransactionTestCase):
    def test_only_admitted_active_users_in_live_sessions_may_connect(self):
        waiting = get_user_model().objects.create_user(username="waiting-socket")
        Enrollment.objects.create(user=waiting, course=self.course)
        services.request_admission(actor=waiting, session=self.session)
        self.tokens[waiting.pk] = str(AccessToken.for_user(waiting))
        async def run():
            for user in [waiting, self.outsider, self.admin]:
                socket = self.socket(user)
                self.assertFalse((await socket.connect())[0])
                await socket.disconnect()
            scheduled = await database_sync_to_async(self.schedule)()
            socket = self.socket(self.host, session=scheduled)
            self.assertFalse((await socket.connect())[0])
            await socket.disconnect()
        async_to_sync(run)()

    def test_foreign_origin_invalid_credentials_and_query_tokens_are_rejected(self):
        async def run():
            cases = [[(b"authorization", f"Bearer {self.tokens[self.learner.pk]}".encode()), (b"origin", b"https://attacker.example")],
                     [(b"authorization", b"Bearer invalid"), (b"origin", b"https://testserver")],
                     [(b"origin", b"https://testserver")]]
            for headers in cases:
                socket = self.socket(headers=headers)
                self.assertFalse((await socket.connect())[0])
                await socket.disconnect()
            for query in ["connection_id=invalid", "connection_id=" + str(uuid4()) + "&token=secret",
                          "connection_id=" + str(uuid4()) + "&connection_id=" + str(uuid4())]:
                socket = self.socket(self.learner, query=query)
                self.assertFalse((await socket.connect())[0])
                await socket.disconnect()
        async_to_sync(run)()

    def test_peer_targeted_offer_answer_and_ice_with_server_identity(self):
        async def run():
            first, _ = await self.open_socket(self.learner)
            second, _ = await self.open_socket(self.other)
            third, _ = await self.open_socket(self.host)
            for socket in [first, second, third]:
                await self.drain(socket)
            await first.send_json_to(self.offer(self.second_participant.pk))
            result = await self.next_type(second, "offer")
            self.assertEqual(result["sender_id"], self.learner.pk)
            self.assertEqual(result["sender_participant_id"], self.first_participant.pk)
            self.assertEqual(result["session_id"], self.session.pk)
            self.assertNotIn("connection_id", result)
            self.assertTrue(await third.receive_nothing(timeout=0.1))
            await second.send_json_to({"type": "answer", "recipient_id": self.first_participant.pk,
                "description": {"type": "answer", "sdp": SDP}})
            await self.next_type(first, "answer")
            await first.send_json_to({"type": "ice_candidate", "recipient_id": self.second_participant.pk, "candidate": ICE})
            await self.next_type(second, "ice_candidate")
            for socket in [first, second, third]:
                await socket.disconnect()
        async_to_sync(run)()

    def test_cross_session_offline_self_and_waiting_recipients_are_rejected(self):
        other_session = self.schedule()
        services.start_session(actor=self.host, session=other_session)
        other_target = self.admit(self.other, session=other_session)
        async def run():
            first, _ = await self.open_socket(self.learner)
            outside, _ = await self.open_socket(self.other, session=other_session)
            for recipient in [other_target.pk, self.first_participant.pk, self.second_participant.pk, 999999]:
                await first.send_json_to(self.offer(recipient))
                result = await self.next_type(first, "error")
                self.assertEqual(result["code"], "invalid_recipient")
            self.assertTrue(await outside.receive_nothing(timeout=0.1))
            await first.disconnect()
            await outside.disconnect()
        async_to_sync(run)()

    def test_presence_exposes_only_admitted_online_peers(self):
        async def run():
            first, ready = await self.open_socket(self.learner)
            self.assertEqual(ready["peers"], [])
            second, ready = await self.open_socket(self.other)
            self.assertEqual(len(ready["peers"]), 1)
            self.assertEqual(ready["peers"][0]["participant_id"], self.first_participant.pk)
            self.assertEqual(ready["peers"][0]["user_id"], self.learner.pk)
            self.assertEqual(ready["peers"][0]["role"], "LEARNER")
            presence = await self.next_type(first, "presence")
            self.assertEqual(presence["peers"][0]["participant_id"], self.second_participant.pk)
            self.assertEqual(set(presence["peers"][0]), {"participant_id", "user_id", "role", "generation"})
            await second.disconnect()
            self.assertEqual((await self.next_type(first, "presence"))["peers"], [])
            await first.disconnect()
        async_to_sync(run)()

    def test_reconnect_fences_old_socket_and_stale_disconnect(self):
        async def run():
            first, ready = await self.open_socket(self.learner)
            second, ready2 = await self.open_socket(self.learner)
            self.assertNotEqual(ready["connection_id"], ready2["connection_id"])
            self.assertEqual(await self.close_code(first), 4409)
            await first.disconnect()
            await second.send_json_to({"type": "ping"})
            await self.next_type(second, "pong")
            count = await database_sync_to_async(AttendanceInterval.objects.filter(
                participant=self.first_participant, left_at__isnull=True).count)()
            self.assertEqual(count, 1)
            await second.disconnect()
        async_to_sync(run)()

    def test_same_open_uuid_takeover_cannot_be_closed_by_older_socket(self):
        connection = uuid4()
        async def run():
            first, _ = await self.open_socket(self.learner, connection=connection)
            second, _ = await self.open_socket(self.learner, connection=connection)
            self.assertEqual(await self.close_code(first), 4409)
            await first.disconnect()
            await second.send_json_to({"type": "ping"})
            await self.next_type(second, "pong")
            await second.disconnect()
        async_to_sync(run)()
        self.assertEqual(AttendanceInterval.objects.filter(participant=self.first_participant).count(), 1)

    def test_fast_reconnect_is_visible_even_when_participant_identity_is_unchanged(self):
        async def run():
            observer, _ = await self.open_socket(self.other)
            first, old = await self.open_socket(self.learner)
            await self.drain(observer)
            second, new = await self.open_socket(self.learner, connection=old["connection_id"])
            self.assertNotEqual(old["generation"], new["generation"])
            for _ in range(4):
                event = await self.next_type(observer, "presence")
                if any(peer["participant_id"] == self.first_participant.pk and peer["generation"] == new["generation"] for peer in event["peers"]):
                    break
            else:
                self.fail("Peer reconnect generation was not announced")
            self.assertEqual(await self.close_code(first), 4409)
            await first.disconnect()
            await second.disconnect()
            await observer.disconnect()
        async_to_sync(run)()

    def test_removed_participant_is_closed_without_sending_a_frame(self):
        async def run():
            first, _ = await self.open_socket(self.learner)
            await database_sync_to_async(services.remove_participant)(actor=self.host, session=self.session, participant=self.first_participant)
            self.assertEqual(await self.close_code(first), 4403)
            await first.disconnect()
        async_to_sync(run)()

    def test_session_end_closes_all_sockets_and_attendance(self):
        async def run():
            first, _ = await self.open_socket(self.learner)
            second, _ = await self.open_socket(self.other)
            await database_sync_to_async(services.end_session)(actor=self.host, session=self.session)
            self.assertEqual(await self.close_code(first), 4410)
            self.assertEqual(await self.close_code(second), 4410)
            await first.disconnect()
            await second.disconnect()
        async_to_sync(run)()
        self.assertFalse(AttendanceInterval.objects.filter(participant__session=self.session, left_at__isnull=True).exists())

    @override_settings(CLASSROOM_WS_HEARTBEAT_SECONDS=0.05)
    def test_idle_jwt_expiry_closes_socket_without_refresh_in_place(self):
        token = AccessToken.for_user(self.learner)
        token.set_exp(lifetime=timedelta(seconds=2))
        self.tokens[self.learner.pk] = str(token)
        async def run():
            socket, _ = await self.open_socket(self.learner)
            self.assertEqual(await self.close_code(socket), 4401)
            await socket.disconnect()
        async_to_sync(run)()

    @override_settings(CLASSROOM_WS_HEARTBEAT_SECONDS=0.05)
    def test_watchdog_detects_revocation_when_control_delivery_is_lost(self):
        async def run():
            socket, _ = await self.open_socket(self.learner)
            await database_sync_to_async(Enrollment.objects.filter(user=self.learner, course=self.course).delete)()
            self.assertEqual(await self.close_code(socket), 4403)
            await socket.disconnect()
        async_to_sync(run)()

    def test_malformed_spoofed_binary_and_oversized_frames_are_not_relayed(self):
        async def run():
            first, _ = await self.open_socket(self.learner)
            second, _ = await self.open_socket(self.other)
            await self.drain(first)
            for text in ["[]", "{", json.dumps({**self.offer(self.second_participant.pk), "sender_id": self.host.pk})]:
                await first.send_to(text_data=text)
                await self.next_type(first, "error")
                self.assertTrue(await second.receive_nothing(timeout=0.05))
            await first.send_to(bytes_data=b"binary")
            self.assertEqual(await self.close_code(first), 1003)
            await first.disconnect()
            await second.disconnect()
            large, _ = await self.open_socket(self.learner)
            await large.send_to(text_data="x" * (signaling.MAX_FRAME_BYTES + 1))
            self.assertEqual(await self.close_code(large), 1009)
            await large.disconnect()
        async_to_sync(run)()

    def test_queued_signal_from_removed_or_replaced_source_is_not_delivered(self):
        async def run():
            source, ready = await self.open_socket(self.learner)
            target, ready2 = await self.open_socket(self.other)
            await self.drain(source)
            source_interval = await database_sync_to_async(AttendanceInterval.objects.get)(connection_id=ready["connection_id"])
            target_interval = await database_sync_to_async(AttendanceInterval.objects.get)(connection_id=ready2["connection_id"])
            event = {"type": "classroom_signal", "session_id": self.session.pk,
                "recipient_id": self.second_participant.pk, "recipient_connection": ready2["connection_id"],
                "recipient_channel": target_interval.signaling_channel_name, "sender_id": self.first_participant.pk,
                "sender_connection": ready["connection_id"], "sender_channel": source_interval.signaling_channel_name,
                "sender_deadline": None, "payload": self.offer(self.second_participant.pk)}
            await database_sync_to_async(services.remove_participant)(actor=self.host, session=self.session, participant=self.first_participant)
            await self.close_code(source)
            await self.drain(target)
            await get_channel_layer().group_send(participant_group(self.session.pk, self.second_participant.pk), event)
            self.assertTrue(await target.receive_nothing(timeout=0.1))
            await source.disconnect()
            await target.disconnect()
        async_to_sync(run)()

    def test_session_cookie_authentication_and_invalid_bearer_override(self):
        self.client.force_login(self.learner)
        cookie = f"{settings.SESSION_COOKIE_NAME}={self.client.cookies[settings.SESSION_COOKIE_NAME].value}".encode()
        async def run():
            headers = [(b"cookie", cookie), (b"origin", b"https://testserver")]
            socket = self.socket(headers=headers)
            self.assertTrue((await socket.connect())[0])
            await socket.receive_json_from()
            await socket.disconnect()
            invalid = self.socket(headers=headers + [(b"authorization", b"Bearer invalid")])
            self.assertFalse((await invalid.connect())[0])
            await invalid.disconnect()
        async_to_sync(run)()

    def test_redis_registration_failure_fails_closed_and_closes_attendance(self):
        async def run():
            layer = get_channel_layer()
            with patch.object(layer, "group_add", AsyncMock(side_effect=RedisError("test unavailable"))):
                with self.assertLogs("learning.consumers", level="ERROR"):
                    socket = self.socket(self.learner)
                    connected, code = await socket.connect()
                self.assertFalse(connected)
                self.assertEqual(code, 1013)
                await socket.disconnect()
        async_to_sync(run)()
        self.assertFalse(AttendanceInterval.objects.filter(participant=self.first_participant, left_at__isnull=True).exists())

    def test_socket_cannot_claim_another_users_connection_uuid(self):
        async def run():
            first, ready = await self.open_socket(self.learner)
            thief = self.socket(self.other, connection=ready["connection_id"])
            self.assertFalse((await thief.connect())[0])
            await thief.disconnect()
            await first.send_json_to({"type": "ping"})
            await self.next_type(first, "pong")
            await first.disconnect()
        async_to_sync(run)()

    def test_session_logout_and_account_deactivation_revoke_open_sockets(self):
        self.client.force_login(self.learner)
        cookie = f"{settings.SESSION_COOKIE_NAME}={self.client.cookies[settings.SESSION_COOKIE_NAME].value}".encode()
        async def run():
            browser = self.socket(headers=[(b"cookie", cookie), (b"origin", b"https://testserver")])
            self.assertTrue((await browser.connect())[0])
            await browser.receive_json_from()
            await database_sync_to_async(self.client.logout)()
            await browser.send_json_to({"type": "ping"})
            self.assertEqual(await self.close_code(browser), 4401)
            await browser.disconnect()
            native, _ = await self.open_socket(self.other)
            await database_sync_to_async(get_user_model().objects.filter(pk=self.other.pk).update)(is_active=False)
            await native.send_json_to({"type": "ping"})
            self.assertEqual(await self.close_code(native), 4401)
            await native.disconnect()
        async_to_sync(run)()

    def test_rate_limit_closes_socket_without_unbounded_relay(self):
        async def run():
            with patch("learning.consumers.signaling_clock", return_value=0):
                socket, _ = await self.open_socket(self.learner)
                for _ in range(61):
                    await socket.send_json_to({"type": "ping"})
                self.assertEqual(await self.close_code(socket), 4408)
            await socket.disconnect()
        async_to_sync(run)()

    def test_stale_presence_lease_is_hidden_and_cannot_relay(self):
        connection = uuid4()
        signaling.prepare_connection(actor=self.learner, session_id=self.session.pk, connection_id=connection, channel_name="expired-test-channel")
        signaling.renew_connection(session_id=self.session.pk, user_id=self.learner.pk,
            connection_id=connection, channel_name="expired-test-channel", activate=True)
        AttendanceInterval.objects.filter(connection_id=connection).update(
            signaling_heartbeat_at=timezone.now() - timedelta(seconds=signaling.lease_seconds() + 1))
        self.assertEqual(signaling.peers(self.session.pk, self.second_participant.pk), [])
        self.assertEqual(signaling.connection_state(self.session.pk, self.learner.pk, connection, "expired-test-channel"), "replaced")

    def test_removal_control_is_sent_only_after_commit_and_not_on_rollback(self):
        from django.db import transaction
        async def run():
            socket, _ = await self.open_socket(self.learner)
            def rollback():
                try:
                    with transaction.atomic():
                        services.remove_participant(actor=self.host, session=self.session, participant=self.first_participant)
                        raise RuntimeError("rollback")
                except RuntimeError:
                    pass
            await database_sync_to_async(rollback)()
            self.assertTrue(await socket.receive_nothing(timeout=0.1))
            await socket.send_json_to({"type": "ping"})
            await self.next_type(socket, "pong")
            await socket.disconnect()
        async_to_sync(run)()

    def test_existing_call_and_user_routes_are_preserved(self):
        from config.asgi import application
        async def run():
            socket = WebsocketCommunicator(application, "/ws/user/", headers=[
                (b"authorization", f"Bearer {self.tokens[self.learner.pk]}".encode())])
            self.assertTrue((await socket.connect())[0])
            self.assertEqual((await socket.receive_json_from())["type"], "user_connection")
            await socket.disconnect()
        async_to_sync(run)()


TEST_REDIS_URL = os.environ.get("CLASSROOM_TEST_REDIS_URL")


@override_settings(ALLOWED_HOSTS=["testserver"])
class ClassroomRedisIntegrationTests(SocketFixture, TransactionTestCase):
    @skipUnless(TEST_REDIS_URL, "Set CLASSROOM_TEST_REDIS_URL to a dedicated test Redis instance.")
    def test_redis_layer_relay_and_revocation(self):
        config = {"default": {"BACKEND": "channels_redis.core.RedisChannelLayer", "CONFIG": {
            "hosts": [TEST_REDIS_URL], "prefix": "classroom-test-" + uuid4().hex}}}
        with override_settings(CHANNEL_LAYERS=config):
            async def run():
                first, _ = await self.open_socket(self.learner)
                second, _ = await self.open_socket(self.other)
                await self.drain(first)
                await first.send_json_to(self.offer(self.second_participant.pk))
                await self.next_type(second, "offer")
                await database_sync_to_async(services.remove_participant)(actor=self.host, session=self.session, participant=self.first_participant)
                self.assertEqual(await self.close_code(first), 4403)
                await first.disconnect()
                await second.disconnect()
                await get_channel_layer().close_pools()
            async_to_sync(run)()

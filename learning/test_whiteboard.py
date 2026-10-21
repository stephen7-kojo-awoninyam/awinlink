from unittest.mock import patch
from uuid import uuid4

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from . import classroom_services, whiteboard_services as board
from .models import AttendanceInterval, Enrollment, Whiteboard, WhiteboardOperation
from .test_classroom_security import ClassroomFixture


def drawing(kind="rectangle"):
    result = {"id": str(uuid4()), "kind": kind, "color": "#123abc", "width": .01}
    if kind == "stroke":
        result["points"] = [[0, 0], [.5, 1]]
    elif kind == "text":
        result.update(x=.1, y=.2, text="Plain text", size=.05)
    else:
        result.update(x=.1, y=.2, w=.3, h=.4)
    return result


class BoardFixture(ClassroomFixture):
    def setUp(self):
        self.delivery = patch("notifications.signals.publish_notification")
        self.delivery.start()
        self.addCleanup(self.delivery.stop)
        super().setUp()
        self.learner_participant = self.admit()

    def state(self, user=None):
        return board.snapshot(actor=user or self.host, session_id=self.session.pk)

    def data(self, action="add", payload=None):
        return {"operation_id": str(uuid4()), "base_revision": self.state()["revision"],
                "action": action, "payload": drawing() if payload is None else payload}

    def apply(self, action="add", payload=None, user=None):
        return board.command(actor=user or self.host, session_id=self.session.pk, data=self.data(action, payload))

    def grant(self, allowed=True):
        return self.apply("permission", {"participant_id": self.learner_participant.pk, "allowed": allowed})


class WhiteboardSecurityTests(BoardFixture, TestCase):
    def test_view_only_default_grants_and_immediate_revocation(self):
        self.assertFalse(self.state(self.learner)["can_edit"])
        with self.assertRaises(PermissionDenied):
            self.apply(user=self.learner)
        self.grant()
        self.apply(user=self.learner)
        self.grant(False)
        with self.assertRaises(PermissionDenied):
            self.apply(user=self.learner)
        self.assertEqual(len(self.state()["objects"]), 1)

    def test_only_host_controls_permissions_and_clear(self):
        for user in [self.cohost, self.learner, self.admin, self.other]:
            for action, payload in [("clear", {}), ("permission", {"participant_id": self.learner_participant.pk, "allowed": True})]:
                with self.subTest(user=user, action=action), self.assertRaises(PermissionDenied):
                    self.apply(action, payload, user)
        self.apply(user=self.cohost)

    def test_all_object_types_persist_erase_undo_and_clear(self):
        for kind in ["stroke", "text", "rectangle", "ellipse", "line"]:
            self.apply(payload=drawing(kind))
        state = self.state()
        ids = list(state["objects"])
        self.apply("erase", {"ids": ids[:2]})
        self.assertEqual(len(self.state()["objects"]), 3)
        self.apply("undo", {})
        self.assertEqual(self.state()["objects"], state["objects"])
        self.apply("clear", {})
        self.assertEqual(self.state()["objects"], {})
        self.apply("undo", {})
        self.assertEqual(self.state()["objects"], state["objects"])
        self.assertEqual(WhiteboardOperation.objects.count(), 9)

    def test_conflict_idempotency_and_actor_binding(self):
        data = self.data()
        result = board.command(actor=self.host, session_id=self.session.pk, data=data)
        self.assertEqual(board.command(actor=self.host, session_id=self.session.pk, data=data)["revision"], result["revision"])
        self.assertEqual(WhiteboardOperation.objects.count(), 1)
        with self.assertRaises(PermissionDenied):
            board.command(actor=self.cohost, session_id=self.session.pk, data=data)
        forged = {**data, "payload": drawing()}
        with self.assertRaises(PermissionDenied):
            board.command(actor=self.host, session_id=self.session.pk, data=forged)
        stale = {**data, "operation_id": str(uuid4())}
        with self.assertRaises(board.RevisionConflict):
            board.command(actor=self.host, session_id=self.session.pk, data=stale)

    def test_undo_cannot_overwrite_another_edit(self):
        self.apply()
        self.apply(user=self.cohost)
        with self.assertRaises(ValidationError):
            self.apply("undo", {})
        self.apply("undo", {}, self.cohost)
        with self.assertRaises(ValidationError):
            self.apply("undo", {}, self.cohost)

    def test_unauthorized_reads_and_current_enrollment(self):
        for user in [self.admin, self.other]:
            with self.assertRaises(PermissionDenied):
                self.state(user)
        Enrollment.objects.filter(user=self.learner).delete()
        with self.assertRaises(PermissionDenied):
            self.state(self.learner)

    def test_removal_and_end_make_stale_clients_safe(self):
        self.grant()
        classroom_services.remove_participant(actor=self.host, session=self.session, participant=self.learner_participant)
        with self.assertRaises(PermissionDenied):
            self.state(self.learner)
        classroom_services.end_session(actor=self.host, session=self.session)
        self.assertFalse(self.state()["can_edit"])
        with self.assertRaises(PermissionDenied):
            self.apply()

    def test_readmission_requires_a_new_editing_grant(self):
        self.grant()
        classroom_services.remove_participant(actor=self.host, session=self.session, participant=self.learner_participant)
        classroom_services.admit_participant(actor=self.host, session=self.session, participant=self.learner_participant)
        self.assertFalse(self.state(self.learner)["can_edit"])
        with self.assertRaises(PermissionDenied):
            self.apply(user=self.learner)

    def test_cross_session_grant_and_transaction_rollback(self):
        other = self.schedule()
        participant = self.admit(session=other)
        with self.assertRaises(PermissionDenied):
            self.apply("permission", {"participant_id": participant.pk, "allowed": True})
        with patch("learning.whiteboard_services.WhiteboardOperation.objects.create", side_effect=ValidationError("fail")):
            with self.assertRaises(ValidationError):
                self.apply()
        self.assertEqual(self.state()["revision"], 0)
        self.assertEqual(self.state()["objects"], {})

    def test_http_rejects_duplicates_nonfinite_and_large_commands(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.host)}")
        url = f"/api/learning/sessions/{self.session.pk}/whiteboard/"
        for raw in ['{"action":"add","action":"clear"}', '{"x":NaN}', 'x' * 65537]:
            self.assertEqual(client.generic("POST", url, raw, content_type="application/json").status_code, 400)

    def test_invalid_values_unknown_fields_and_limits_roll_back(self):
        base = drawing()
        invalid = [{**base, "x": True}, {**base, "x": float("nan")}, {**base, "x": 2},
            {**base, "kind": []}, {**base, "url": "https://evil"}, {**base, "id": "bad"},
            {**drawing("stroke"), "points": [[0, 0]]}, {**drawing("text"), "text": "x" * 2001}]
        for obj in invalid:
            with self.subTest(obj=obj), self.assertRaises(ValidationError):
                self.apply(payload=obj)
        self.assertEqual(WhiteboardOperation.objects.count(), 0)
        self.assertEqual(self.state()["revision"], 0)
        with self.assertRaises(ValidationError):
            board.command(actor=self.host, session_id=self.session.pk, data={**self.data(), "actor_id": self.admin.pk})

    def test_database_bulk_validation_and_immutable_log(self):
        self.apply()
        current = Whiteboard.objects.get(session=self.session)
        with self.assertRaises(ValidationError):
            Whiteboard.objects.filter(pk=current.pk).update(objects_data={"bad": drawing()})
        with self.assertRaises(ValidationError):
            WhiteboardOperation.objects.all().update(action="clear")
        current.objects_data = {"bad": drawing()}
        with self.assertRaises(ValidationError):
            Whiteboard.objects.bulk_update([current], ["objects_data"])

    def test_http_authentication_errors_and_safe_conflicts(self):
        url = f"/api/learning/sessions/{self.session.pk}/whiteboard/"
        client = APIClient()
        self.assertIn(client.get(url).status_code, [401, 403])
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.learner)}")
        self.assertEqual(client.get(url).status_code, 200)
        self.assertEqual(client.post(url, self.data(), format="json").status_code, 403)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.host)}")
        data = self.data()
        self.assertEqual(client.post(url, data, format="json").status_code, 200)
        data["operation_id"] = str(uuid4())
        response = client.post(url, data, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["error"]["code"], "conflict")
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.admin)}")
        self.assertEqual(client.get(url).status_code, 403)


@override_settings(ALLOWED_HOSTS=["testserver"], CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}, CLASSROOM_WS_HEARTBEAT_SECONDS=.05)
class WhiteboardSocketTests(BoardFixture, TransactionTestCase):
    def socket(self, user=None, session=None, token=None, headers=None):
        from config.asgi import application
        if headers is None:
            headers = [(b"authorization", f"Bearer {token or AccessToken.for_user(user)}".encode())] if user else []
        return WebsocketCommunicator(application, f"/ws/learning/sessions/{(session or self.session).pk}/whiteboard/", headers=headers)

    async def open(self, user):
        socket = self.socket(user)
        self.assertTrue((await socket.connect(timeout=5))[0])
        state = await socket.receive_json_from(timeout=5)
        self.assertEqual(state["type"], "snapshot")
        return socket, state

    async def until(self, socket, kind):
        for _ in range(10):
            value = await socket.receive_json_from(timeout=5)
            if value["type"] == kind:
                return value
        self.fail("Missing message")

    def test_auth_admission_origin_and_invalid_json(self):
        async def run():
            for user in [None, self.other, self.admin]:
                socket = self.socket(user)
                self.assertFalse((await socket.connect())[0])
                await socket.disconnect()
            socket = self.socket(self.host, headers=[(b"origin", b"https://evil.example"),
                (b"authorization", f"Bearer {AccessToken.for_user(self.host)}".encode())])
            self.assertFalse((await socket.connect())[0])
            await socket.disconnect()
            socket, _ = await self.open(self.host)
            await socket.send_to(text_data='{"action":"clear","action":"add"}')
            self.assertEqual((await self.until(socket, "error"))["code"], "invalid_request")
            await socket.disconnect()
        async_to_sync(run)()

    def test_sync_reconnect_persistence_and_readonly_denial(self):
        async def run():
            host, state = await self.open(self.host)
            learner, _ = await self.open(self.learner)
            obj = drawing()
            data = {"operation_id": str(uuid4()), "base_revision": state["revision"], "action": "add", "payload": obj}
            await learner.send_json_to(data)
            self.assertEqual((await self.until(learner, "error"))["code"], "permission_denied")
            await host.send_json_to(data)
            self.assertEqual((await self.until(host, "ack"))["revision"], 1)
            synced = await self.until(learner, "snapshot")
            self.assertEqual(synced["objects"][obj["id"]], obj)
            await learner.disconnect()
            learner, recovered = await self.open(self.learner)
            self.assertEqual(recovered["objects"], synced["objects"])
            self.assertEqual(await database_sync_to_async(AttendanceInterval.objects.count)(), 0)
            await host.disconnect(); await learner.disconnect()
        async_to_sync(run)()

    def test_revocation_removal_and_end(self):
        self.grant()
        async def run():
            learner, state = await self.open(self.learner)
            self.assertTrue(state["can_edit"])
            await database_sync_to_async(self.grant)(False)
            self.assertFalse((await self.until(learner, "snapshot"))["can_edit"])
            await database_sync_to_async(classroom_services.remove_participant)(actor=self.host,
                session=self.session, participant=self.learner_participant)
            output = await learner.receive_output()
            self.assertEqual(output["type"], "websocket.close")
            self.assertEqual(output["code"], 4403)
            await learner.disconnect()
            host, _ = await self.open(self.host)
            await database_sync_to_async(classroom_services.end_session)(actor=self.host, session=self.session)
            self.assertFalse((await self.until(host, "snapshot"))["can_edit"])
            await host.disconnect()
        async_to_sync(run)()

    def test_idle_jwt_expiry(self):
        import time
        token = AccessToken.for_user(self.host)
        token["exp"] = int(time.time()) + 2
        async def run():
            socket = self.socket(self.host, token=str(token))
            self.assertTrue((await socket.connect())[0])
            await socket.receive_json_from()
            output = await socket.receive_output(timeout=3)
            self.assertEqual(output["type"], "websocket.close")
            self.assertEqual(output["code"], 4401)
            await socket.disconnect()
        async_to_sync(run)()

    def test_room_isolation_and_room_identity_injection(self):
        other = self.schedule()
        classroom_services.start_session(actor=self.host, session=other)
        async def run():
            first, state = await self.open(self.host)
            second = self.socket(self.host, session=other)
            self.assertTrue((await second.connect())[0])
            await second.receive_json_from()
            data = {"operation_id": str(uuid4()), "base_revision": state["revision"], "action": "add", "payload": drawing()}
            await first.send_json_to({**data, "session_id": other.pk})
            self.assertEqual((await self.until(first, "error"))["code"], "invalid_request")
            await first.send_json_to(data)
            await self.until(first, "ack")
            self.assertTrue(await second.receive_nothing(timeout=.15))
            await first.disconnect(); await second.disconnect()
        async_to_sync(run)()

    def test_whiteboard_reconnect_preserves_live_signaling_connection(self):
        from config.asgi import application
        connection = uuid4()
        async def run():
            signaling = WebsocketCommunicator(application,
                f"/ws/learning/sessions/{self.session.pk}/?connection_id={connection}",
                headers=[(b"authorization", f"Bearer {AccessToken.for_user(self.learner)}".encode())])
            self.assertTrue((await signaling.connect())[0])
            await signaling.receive_json_from()
            before = await database_sync_to_async(AttendanceInterval.objects.values().get)(connection_id=connection)
            whiteboard, _ = await self.open(self.learner)
            await whiteboard.disconnect()
            whiteboard, _ = await self.open(self.learner)
            await whiteboard.disconnect()
            after = await database_sync_to_async(AttendanceInterval.objects.values().get)(connection_id=connection)
            self.assertIsNone(after["left_at"])
            self.assertEqual(before["signaling_channel_name"], after["signaling_channel_name"])
            await signaling.send_json_to({"type": "ping"})
            self.assertEqual((await self.until(signaling, "pong"))["type"], "pong")
            await signaling.disconnect()
        async_to_sync(run)()

    def test_binary_oversized_frames_and_rate_limit(self):
        async def run():
            for payload, code in [(b"drawing", 4400), ("x" * 65537, 4400)]:
                socket, _ = await self.open(self.host)
                if isinstance(payload, bytes):
                    await socket.send_to(bytes_data=payload)
                else:
                    await socket.send_to(text_data=payload)
                self.assertEqual((await socket.receive_output())["code"], code)
                await socket.disconnect()
            with patch("learning.whiteboard_consumer.whiteboard_clock", return_value=0):
                socket, _ = await self.open(self.host)
                for _ in range(31):
                    await socket.send_json_to({"type": "snapshot"})
                for _ in range(40):
                    output = await socket.receive_output()
                    if output["type"] == "websocket.close":
                        self.assertEqual(output["code"], 4408)
                        break
                else:
                    self.fail("Missing rate limit close")
                await socket.disconnect()
        async_to_sync(run)()

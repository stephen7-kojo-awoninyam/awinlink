import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from django.contrib.auth import get_user_model
from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import AccessToken

from .consumers import CallConsumer


class SignalingPayloadTests(SimpleTestCase):
    def setUp(self):
        # These tests isolate signal payload handling; credential integration is
        # exercised independently by real ASGI communicators below.
        guard = patch('messaging.socket_security.SecureSocketMixin.ensure_credentials', new=AsyncMock(return_value=True))
        guard.start()
        self.addCleanup(guard.stop)

    def test_non_object_json_does_not_crash_or_relay(self):
        for payload in ('[]', 'null', '42', '"offer"'):
            consumer = CallConsumer()
            consumer.user = SimpleNamespace(id=1)
            consumer.room_group_name = 'call_1'
            consumer.channel_name = 'sender'
            consumer.channel_layer = SimpleNamespace(group_send=AsyncMock())
            consumer.send = AsyncMock()
            consumer.check_participant = AsyncMock(return_value=True)
            async_to_sync(consumer.receive)(payload)
            consumer.channel_layer.group_send.assert_not_awaited()
            self.assertEqual(json.loads(consumer.send.call_args.kwargs['text_data'])['type'], 'error')

    def test_sender_identity_is_server_controlled(self):
        consumer = CallConsumer()
        consumer.user = SimpleNamespace(id=7)
        consumer.room_group_name = 'call_1'
        consumer.channel_name = 'sender'
        consumer.channel_layer = SimpleNamespace(group_send=AsyncMock())
        consumer.check_participant = AsyncMock(return_value=True)
        async_to_sync(consumer.receive)('{"type":"offer","sender_id":99}')
        self.assertEqual(consumer.channel_layer.group_send.call_args.args[1]['data']['sender_id'], 7)

    def test_revoked_participant_cannot_keep_relaying_on_open_socket(self):
        consumer = CallConsumer()
        consumer.check_participant = AsyncMock(return_value=False)
        consumer.close = AsyncMock()
        consumer.channel_layer = SimpleNamespace(group_send=AsyncMock())
        async_to_sync(consumer.receive)('{"type":"offer"}')
        consumer.close.assert_awaited_once_with(code=4003)
        consumer.channel_layer.group_send.assert_not_awaited()

    def test_binary_frame_returns_error_instead_of_type_error(self):
        consumer = CallConsumer()
        consumer.check_participant = AsyncMock(return_value=True)
        consumer.send = AsyncMock()
        consumer.close = AsyncMock()
        async_to_sync(consumer.receive)(bytes_data=b'not a text signal')
        consumer.close.assert_awaited_once_with(code=1003)
        consumer.send.assert_not_awaited()

    def test_legacy_web_payloads_are_normalized_for_mobile(self):
        for payload in (
            {"type": "offer", "target_id": 2, "offer": {"type": "offer", "sdp": "legacy"}},
            {"type": "ice-candidate", "target_id": 2, "candidate": {"candidate": "ice"}},
        ):
            consumer = CallConsumer()
            consumer.user = SimpleNamespace(id=1)
            consumer.room_group_name = 'call_1'
            consumer.channel_name = 'sender'
            consumer.channel_layer = SimpleNamespace(group_send=AsyncMock())
            consumer.check_participant = AsyncMock(return_value=True)
            async_to_sync(consumer.receive)(json.dumps(payload))
            data = consumer.channel_layer.group_send.call_args.args[1]['data']
            self.assertEqual(data['to_user_id'], 2)
            if payload['type'] == 'offer':
                self.assertEqual(data['description'], payload['offer'])
            else:
                self.assertEqual(data['type'], 'ice_candidate')

    def test_directed_signals_only_reach_recipient(self):
        consumer = CallConsumer()
        consumer.user = SimpleNamespace(id=3)
        consumer.channel_name = 'third-peer'
        consumer.send = AsyncMock()
        event = {'sender_channel': 'sender', 'data': {'type': 'answer', 'to_user_id': 2}}
        async_to_sync(consumer.call_signal)(event)
        consumer.send.assert_not_awaited()
        consumer.user.id = 2
        async_to_sync(consumer.call_signal)(event)
        consumer.send.assert_awaited_once()

    def test_invalid_target_returns_error(self):
        consumer = CallConsumer()
        consumer.user = SimpleNamespace(id=1)
        consumer.check_participant = AsyncMock(return_value=True)
        consumer.send = AsyncMock()
        consumer.channel_layer = SimpleNamespace(group_send=AsyncMock())
        async_to_sync(consumer.receive)(json.dumps({'type': 'ready', 'to_user_id': 'invalid'}))
        consumer.channel_layer.group_send.assert_not_awaited()
        self.assertEqual(json.loads(consumer.send.call_args.kwargs['text_data'])['type'], 'error')


@override_settings(ALLOWED_HOSTS=['testserver'])
class WebSocketOriginTests(SimpleTestCase):
    def exercise(self, headers, jwt=False):
        from config.asgi import WebSocketOriginMiddleware

        async def accept(scope, receive, send):
            await receive()
            await send({'type': 'websocket.accept'})
            await receive()

        async def run():
            socket = WebsocketCommunicator(WebSocketOriginMiddleware(accept), '/ws/user/', headers=headers)
            socket.scope['jwt_authenticated'] = jwt
            connected, _ = await socket.connect()
            await socket.disconnect()
            return connected

        return async_to_sync(run)()

    def test_foreign_browser_origin_is_rejected_even_with_jwt(self):
        self.assertFalse(self.exercise([(b'origin', b'https://attacker.example')], jwt=True))

    def test_allowed_browser_origin_is_accepted(self):
        self.assertTrue(self.exercise([(b'origin', b'https://testserver')]))

    def test_originless_native_requires_validated_jwt(self):
        self.assertFalse(self.exercise([]))
        self.assertTrue(self.exercise([], jwt=True))


@override_settings(ALLOWED_HOSTS=['testserver'], CHANNEL_LAYERS={
    'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'},
})
class NativeSignalingIntegrationTests(TransactionTestCase):
    def setUp(self):
        from .models import Call, CallParticipant, Conversation, ConversationParticipant
        User = get_user_model()
        self.caller = User.objects.create_user(username='signal_audit_caller')
        self.callee = User.objects.create_user(username='signal_audit_callee')
        self.outsider = User.objects.create_user(username='signal_audit_outsider')
        conversation = Conversation.objects.create(created_by=self.caller)
        for user in (self.caller, self.callee):
            ConversationParticipant.objects.create(conversation=conversation, user=user)
        self.call = Call.objects.create(conversation=conversation, initiated_by=self.caller, call_type='VIDEO')
        for user in (self.caller, self.callee):
            CallParticipant.objects.create(call=self.call, user=user, status='JOINED')
        self.tokens = {user.pk: str(AccessToken.for_user(user)) for user in (self.caller, self.callee, self.outsider)}

    def socket(self, user, origin=None):
        from config.asgi import application
        headers = [(b'authorization', f'Bearer {self.tokens[user.pk]}'.encode())]
        if origin:
            headers.append((b'origin', origin.encode()))
        return WebsocketCommunicator(application, f'/ws/calls/{self.call.pk}/', headers=headers)

    def test_authenticated_native_peers_relay_offer_with_server_identity(self):
        async def run():
            first, second = self.socket(self.caller), self.socket(self.callee)
            self.assertTrue((await first.connect())[0])
            self.assertEqual((await first.receive_json_from())['type'], 'connection')
            self.assertTrue((await second.connect())[0])
            await second.receive_json_from()
            self.assertEqual((await first.receive_json_from())['type'], 'participant_joined')
            await first.send_json_to({'type': 'offer', 'description': {'type': 'offer', 'sdp': 'audit'}, 'sender_id': self.outsider.pk})
            self.assertEqual((await second.receive_json_from())['sender_id'], self.caller.pk)
            await first.disconnect()
            await second.disconnect()
        async_to_sync(run)()

    def test_outsider_and_foreign_browser_are_rejected(self):
        async def run():
            for socket in (self.socket(self.outsider), self.socket(self.caller, 'https://attacker.example')):
                self.assertFalse((await socket.connect())[0])
                await socket.disconnect()
        async_to_sync(run)()

    def test_ended_call_cannot_be_reopened_by_remaining_participant_record(self):
        self.call.status = 'ENDED'
        self.call.save(update_fields=['status'])
        async def run():
            socket = self.socket(self.caller)
            self.assertFalse((await socket.connect())[0])
            await socket.disconnect()
        async_to_sync(run)()

    def test_revocation_takes_effect_on_an_existing_connection(self):
        from .models import CallParticipant
        async def run():
            socket = self.socket(self.caller)
            self.assertTrue((await socket.connect())[0])
            await socket.receive_json_from()
            await database_sync_to_async(CallParticipant.objects.filter(call=self.call, user=self.caller).update)(status='LEFT')
            await socket.send_json_to({'type': 'offer'})
            self.assertEqual((await socket.receive_output())['code'], 4003)
            await socket.disconnect()
        async_to_sync(run)()

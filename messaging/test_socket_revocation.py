import asyncio
from datetime import timedelta

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.test import TransactionTestCase, Client, override_settings
from rest_framework_simplejwt.tokens import AccessToken

from .models import Call, CallParticipant, Conversation, ConversationParticipant


@override_settings(ALLOWED_HOSTS=['testserver'], MESSAGING_WS_HEARTBEAT_SECONDS=0.05,
                   CHANNEL_LAYERS={'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}})
class SocketRevocationTests(TransactionTestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='socket-owner', password='OriginalPassword123!')
        self.other = User.objects.create_user(username='socket-other')
        conversation = Conversation.objects.create(created_by=self.user)
        self.call = Call.objects.create(conversation=conversation, initiated_by=self.user, status='ACTIVE')
        for user in [self.user, self.other]:
            ConversationParticipant.objects.create(conversation=conversation, user=user)
            CallParticipant.objects.create(call=self.call, user=user, status='JOINED')
        self.token = str(AccessToken.for_user(self.user))

    def socket(self, path='/ws/user/', token=None):
        from config.asgi import application
        return WebsocketCommunicator(application, path, headers=[(b'authorization', ('Bearer ' + (token or self.token)).encode())])

    async def connected(self, socket):
        self.assertTrue((await socket.connect())[0])
        await socket.receive_json_from()

    def test_expired_idle_socket_is_closed_without_client_activity(self):
        token = AccessToken.for_user(self.user)
        token.set_exp(lifetime=timedelta(seconds=1))
        async def run():
            socket = self.socket(token=str(token))
            await self.connected(socket)
            self.assertEqual((await socket.receive_output(timeout=2))['code'], 4001)
            await socket.disconnect()
        async_to_sync(run)()

    def test_password_change_stops_passive_notification_delivery(self):
        def change_password():
            self.user.set_password('ChangedPassword123!')
            self.user.save(update_fields=['password'])
        async def run():
            socket = self.socket()
            await self.connected(socket)
            await database_sync_to_async(change_password)()
            await get_channel_layer().group_send(f'user_{self.user.pk}', {'type': 'notification_created', 'notification': {'message': 'must not arrive'}})
            self.assertEqual((await socket.receive_output())['code'], 4001)
            await socket.disconnect()
        async_to_sync(run)()

    def test_revoked_call_participant_cannot_passively_receive_signals(self):
        async def run():
            socket = self.socket(f'/ws/calls/{self.call.pk}/')
            await self.connected(socket)
            await database_sync_to_async(CallParticipant.objects.filter(call=self.call, user=self.user).update)(status='LEFT')
            await get_channel_layer().group_send(f'call_{self.call.pk}', {'type': 'call_signal', 'sender_channel': 'other-device', 'data': {'type': 'offer', 'sender_id': self.other.pk}})
            self.assertEqual((await socket.receive_output())['code'], 4003)
            await socket.disconnect()
        async_to_sync(run)()

    def test_session_logout_invalidates_existing_browser_socket(self):
        from config.asgi import application
        client = Client()
        client.force_login(self.user)
        key = client.session.session_key
        async def run():
            socket = WebsocketCommunicator(application, '/ws/user/', headers=[(b'origin', b'https://testserver'), (b'cookie', ('sessionid=' + key).encode())])
            await self.connected(socket)
            await database_sync_to_async(Session.objects.filter(session_key=key).delete)()
            self.assertEqual((await socket.receive_output())['code'], 4001)
            await socket.disconnect()
        async_to_sync(run)()

    def test_reauthentication_cannot_change_identity(self):
        other_token = str(AccessToken.for_user(self.other))
        async def run():
            socket = self.socket()
            await self.connected(socket)
            await socket.send_json_to({'type': 'reauthenticate', 'access': other_token})
            self.assertEqual((await socket.receive_output())['code'], 4001)
            await socket.disconnect()
        async_to_sync(run)()

    def test_same_user_can_renew_in_place_to_preserve_long_calls(self):
        token = AccessToken.for_user(self.user)
        token.set_exp(lifetime=timedelta(seconds=2))
        fresh = str(AccessToken.for_user(self.user))
        async def run():
            socket = self.socket(f'/ws/calls/{self.call.pk}/', token=str(token))
            await self.connected(socket)
            await socket.send_json_to({'type': 'reauthenticate', 'access': fresh})
            await asyncio.sleep(2.1)
            await get_channel_layer().group_send(f'call_{self.call.pk}', {'type': 'call_signal', 'sender_channel': 'other-device', 'data': {'type': 'ready', 'sender_id': self.other.pk}})
            self.assertEqual((await socket.receive_json_from())['type'], 'ready')
            await socket.disconnect()
        async_to_sync(run)()

    def test_oversized_signal_is_closed_before_parsing(self):
        async def run():
            socket = self.socket(f'/ws/calls/{self.call.pk}/')
            await self.connected(socket)
            await socket.send_to(text_data='x' * 65537)
            self.assertEqual((await socket.receive_output())['code'], 1009)
            await socket.disconnect()
        async_to_sync(run)()

from unittest.mock import patch
from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings
from .consumers import UserConsumer
from .models import Conversation, ConversationParticipant, Message
from .realtime import mark_read
from .serializers import ConversationSerializer
from types import SimpleNamespace


@override_settings(CHANNEL_LAYERS={'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}})
class RealtimeTests(TransactionTestCase):
    def setUp(self):
        self.users = [get_user_model().objects.create_user(username=f'live_{i}') for i in range(3)]
        self.conversation = Conversation.objects.create(is_group=True)
        for user in self.users[:2]:
            ConversationParticipant.objects.create(conversation=self.conversation, user=user)

    def socket(self, user):
        from rest_framework_simplejwt.tokens import AccessToken
        socket = WebsocketCommunicator(UserConsumer.as_asgi(), '/ws/user/')
        socket.scope['user'] = user
        if user.is_authenticated:
            token = AccessToken.for_user(user)
            socket.scope.update(jwt_authenticated=True, jwt_claims=dict(token.payload), jwt_expires_at=token['exp'])
        return socket

    def test_committed_message_and_typing_reach_only_participants(self):
        async def scenario():
            sockets = [self.socket(user) for user in self.users]
            for socket in sockets:
                self.assertTrue((await socket.connect())[0])
                await socket.receive_json_from()
            await database_sync_to_async(Message.objects.create)(
                conversation=self.conversation, sender=self.users[0], content='Live')
            for socket in sockets[:2]:
                event = await socket.receive_json_from()
                self.assertEqual(event['type'], 'message_created')
                self.assertEqual(event['message']['content'], 'Live')
            self.assertTrue(await sockets[2].receive_nothing(timeout=0.05))
            await sockets[0].send_json_to({'type': 'typing', 'conversation_id': self.conversation.pk, 'is_typing': True, 'user_id': 999})
            for socket in sockets[:2]:
                event = await socket.receive_json_from()
                self.assertEqual(event['user_id'], self.users[0].pk)
            await sockets[2].send_json_to({'type': 'typing', 'conversation_id': self.conversation.pk, 'is_typing': True})
            self.assertTrue(await sockets[1].receive_nothing(timeout=0.05))
            await database_sync_to_async(ConversationParticipant.objects.filter(user=self.users[1]).delete)()
            await database_sync_to_async(Message.objects.create)(conversation=self.conversation, sender=self.users[0], content='Private')
            await sockets[0].receive_json_from()
            self.assertTrue(await sockets[1].receive_nothing(timeout=0.05))
            for socket in sockets:
                await socket.disconnect()
        async_to_sync(scenario)()

    def test_group_reads_are_per_participant(self):
        third = self.users[2]
        ConversationParticipant.objects.create(conversation=self.conversation, user=third)
        Message.objects.create(conversation=self.conversation, sender=self.users[0], content='Unread')
        mark_read(self.users[1], self.conversation.pk)
        for user, expected in ((self.users[1], 0), (third, 1)):
            data = ConversationSerializer(self.conversation, context={'request': SimpleNamespace(user=user)}).data
            self.assertEqual(data['unread_count'], expected)
            from core.context_processors import unread_messages
            self.assertEqual(unread_messages(SimpleNamespace(user=user))['unread_message_count'], expected)

    def test_read_marker_never_moves_backwards(self):
        from datetime import timedelta
        from django.utils import timezone
        now = timezone.now()
        mark_read(self.users[1], self.conversation.pk, now)
        mark_read(self.users[1], self.conversation.pk, now - timedelta(minutes=1))
        participant = ConversationParticipant.objects.get(user=self.users[1])
        self.assertEqual(participant.last_read_at, now)

    def test_rollback_does_not_publish(self):
        from django.db import transaction
        with patch('messaging.realtime.publish') as publish:
            try:
                with transaction.atomic():
                    Message.objects.create(conversation=self.conversation, sender=self.users[0], content='Rollback')
                    raise ValueError()
            except ValueError:
                pass
            publish.assert_not_called()

    def test_anonymous_socket_rejected(self):
        from django.contrib.auth.models import AnonymousUser
        async def scenario():
            socket = self.socket(AnonymousUser())
            self.assertFalse((await socket.connect())[0])
            await socket.disconnect()
        async_to_sync(scenario)()

    def test_blocked_participant_cannot_send_or_receive_typing(self):
        from accounts.models import UserBlock
        from .realtime import can_access
        UserBlock.objects.create(user=self.users[0], blocked_user=self.users[1])
        self.assertFalse(can_access(self.users[0], self.conversation.pk))
        self.assertFalse(can_access(self.users[1], self.conversation.pk))

    def test_web_and_api_send_publish_once_after_commit(self):
        from django.test import Client
        from rest_framework.test import APIClient
        from django.urls import reverse
        api = APIClient()
        api.force_authenticate(self.users[0])
        web = Client()
        web.force_login(self.users[0])
        with patch('messaging.realtime.publish') as publish:
            response = api.post(reverse('messaging_api:send_message', args=[self.conversation.pk]), {'content': 'API', 'message_type': 'TEXT'})
            self.assertEqual(response.status_code, 201)
            self.assertEqual(publish.call_count, 1)
            response = web.post(reverse('messaging:send_message', args=[self.conversation.pk]), {'content': 'Web'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
            self.assertEqual(response.status_code, 201)
            self.assertEqual(publish.call_count, 2)

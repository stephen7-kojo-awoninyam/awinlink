from unittest.mock import patch
from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from .consumers import CallConsumer
from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient
from accounts.models import UserBlock
from notifications.models import Notification
from .models import Call, CallParticipant, Conversation, ConversationParticipant


@override_settings(CHANNEL_LAYERS={'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}})
class CallInvitationTests(TestCase):
    def setUp(self):
        self.host, self.member, self.guest = [get_user_model().objects.create_user(username=name) for name in ('host', 'member', 'guest')]
        self.conversation = Conversation.objects.create(created_by=self.host)
        for user in (self.host, self.member):
            ConversationParticipant.objects.create(conversation=self.conversation, user=user)
        self.call = Call.objects.create(conversation=self.conversation, initiated_by=self.host, call_type='VIDEO', status='ACTIVE')
        for user in (self.host, self.member):
            CallParticipant.objects.create(call=self.call, user=user, status='JOINED')
        self.client = APIClient()
        self.client.force_authenticate(self.host)
        self.url = f'/api/messaging/calls/{self.call.pk}/invite/'

    def invite(self, username='guest'):
        return self.client.post(self.url, {'username': username}, format='json')

    def test_guest_receives_invitation_accepts_without_message_history_access(self):
        with patch('messaging.api_views.async_to_sync') as bridge:
            with self.captureOnCommitCallbacks(execute=True), patch('notifications.signals.publish_notification'):
                response = self.invite()
        self.assertEqual(response.status_code, 201, response.data)
        event = bridge.return_value.call_args.args
        self.assertEqual(event[0], f'user_{self.guest.pk}')
        self.assertEqual(event[1]['type'], 'incoming_call')
        self.assertTrue(self.call.participants.get(user=self.guest).is_guest)
        self.assertFalse(self.conversation.participants.filter(user=self.guest).exists())
        self.client.force_authenticate(self.guest)
        self.assertEqual(self.client.get('/api/messaging/calls/incoming/').data[0]['id'], self.call.pk)
        accepted = self.client.post(f'/api/messaging/calls/{self.call.pk}/accept/')
        self.assertEqual(accepted.status_code, 200, accepted.data)
        self.assertEqual(len(accepted.data['participants']), 3)
        denied = self.client.get(f'/api/messaging/conversations/{self.conversation.pk}/messages/')
        self.assertIn(denied.status_code, (403, 404))
        self.assertFalse(Notification.objects.filter(user=self.guest, is_read=False).exists())

    def test_only_joined_members_can_invite_and_only_initiator_invites_guests(self):
        self.client.force_authenticate(self.guest)
        self.assertEqual(self.invite().status_code, 403)
        self.client.force_authenticate(self.member)
        self.assertEqual(self.invite().status_code, 403)
        self.call.participants.filter(user=self.member).update(status='LEFT')
        self.assertEqual(self.invite('host').status_code, 403)

    def test_duplicate_terminal_and_invalid_invites_do_not_notify(self):
        self.assertEqual(self.invite().status_code, 201)
        count = Notification.objects.count()
        self.assertEqual(self.invite().status_code, 409)
        self.assertEqual(Notification.objects.count(), count)
        for value in (None, True, [], 'missing', ''):
            self.assertEqual(self.invite(value).status_code, 400)
        self.call.status = 'ENDED'
        self.call.save()
        self.assertEqual(self.invite().status_code, 409)

    def test_blocked_users_and_capacity_are_enforced(self):
        UserBlock.objects.create(user=self.member, blocked_user=self.guest)
        self.assertEqual(self.invite().status_code, 403)
        UserBlock.objects.all().delete()
        for index in range(6):
            user = get_user_model().objects.create_user(username=f'extra{index}')
            CallParticipant.objects.create(call=self.call, user=user, status='JOINED')
        self.assertEqual(self.invite().status_code, 409)

    def test_declined_guest_can_be_reinvited(self):
        self.assertEqual(self.invite().status_code, 201)
        self.client.force_authenticate(self.guest)
        self.assertEqual(self.client.post(f'/api/messaging/calls/{self.call.pk}/reject/').status_code, 200)
        self.call.refresh_from_db()
        self.assertEqual(self.call.status, 'ACTIVE')
        self.client.force_authenticate(self.host)
        self.assertEqual(self.invite().status_code, 201)

    def test_expired_active_call_invitation_cannot_be_accepted_or_polled(self):
        self.assertEqual(self.invite().status_code, 201)
        self.call.participants.filter(user=self.guest).update(invitation_expires_at=timezone.now() - timedelta(seconds=1))
        self.client.force_authenticate(self.guest)
        self.assertEqual(self.client.get('/api/messaging/calls/incoming/').data, [])
        self.assertEqual(self.client.post(f'/api/messaging/calls/{self.call.pk}/accept/').status_code, 400)


    def test_unaccepted_guest_cannot_end_ongoing_call(self):
        self.assertEqual(self.invite().status_code, 201)
        self.client.force_authenticate(self.guest)
        self.assertEqual(self.client.post(f'/api/messaging/calls/{self.call.pk}/end/').status_code, 403)
        self.call.refresh_from_db()
        self.assertEqual(self.call.status, 'ACTIVE')



@override_settings(ALLOWED_HOSTS=['testserver'], CHANNEL_LAYERS={'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}})
class GuestCallSocketTests(TransactionTestCase):
    def test_browser_token_authentication_allows_guest_only_in_invited_call(self):
        from channels.testing import WebsocketCommunicator
        from rest_framework_simplejwt.tokens import AccessToken
        from config.asgi import application
        user = get_user_model().objects.create_user(username='socket-guest')
        host = get_user_model().objects.create_user(username='socket-host')
        conversation = Conversation.objects.create(created_by=host)
        call = Call.objects.create(conversation=conversation, initiated_by=host, status='ACTIVE')
        CallParticipant.objects.create(call=call, user=user, status='JOINED', is_guest=True)
        CallParticipant.objects.create(call=call, user=host, status='JOINED')
        token = str(AccessToken.for_user(user))
        async def run():
            socket = WebsocketCommunicator(application, f'/ws/calls/{call.pk}/',
                headers=[(b'origin', b'http://testserver')], subprotocols=['bearer', token])
            connected, protocol = await socket.connect()
            self.assertTrue(connected)
            self.assertIsNone(protocol)
            self.assertEqual((await socket.receive_json_from())['type'], 'connection')
            await socket.disconnect()
            other = WebsocketCommunicator(application, f'/ws/calls/{call.pk + 1}/',
                headers=[(b'origin', b'http://testserver')], subprotocols=['bearer', token])
            self.assertFalse((await other.connect())[0])
            await other.disconnect()
        async_to_sync(run)()

    def test_unaccepted_guest_cannot_connect_or_receive_directed_signals(self):
        from channels.testing import WebsocketCommunicator
        from rest_framework_simplejwt.tokens import AccessToken
        from config.asgi import application
        host = get_user_model().objects.create_user(username='consent-host')
        guest = get_user_model().objects.create_user(username='consent-guest')
        conversation = Conversation.objects.create(created_by=host)
        ConversationParticipant.objects.create(conversation=conversation, user=host)
        call = Call.objects.create(conversation=conversation, initiated_by=host, status='ACTIVE')
        CallParticipant.objects.create(call=call, user=host, status='JOINED')
        CallParticipant.objects.create(call=call, user=guest, is_guest=True, status='RINGING',
                                       invitation_expires_at=timezone.now() + timedelta(seconds=30))
        token = str(AccessToken.for_user(guest))
        async def run():
            socket = WebsocketCommunicator(application, f'/ws/calls/{call.pk}/',
                headers=[(b'origin', b'http://testserver')], subprotocols=['bearer', token])
            self.assertFalse((await socket.connect())[0])
            await socket.disconnect()
            consumer = CallConsumer()
            consumer.call_id, consumer.user = call.pk, host
            self.assertFalse(await consumer.target_is_participant(guest.pk))
            await database_sync_to_async(lambda: call.participants.filter(user=guest).update(status='JOINED'))()
            self.assertTrue(await consumer.target_is_participant(guest.pk))
        async_to_sync(run)()

from unittest.mock import patch
from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient
from notifications.models import Notification
from .consumers import CallConsumer, UserConsumer
from .models import Call, CallParticipant, Conversation, ConversationParticipant


class CallCancellationTests(TransactionTestCase):
    # Channels closes old connections at async boundaries. TestCase's outer
    # atomic block makes that close the PostgreSQL connection mid-test.
    captureOnCommitCallbacks = TestCase.captureOnCommitCallbacks

    def setUp(self):
        self.caller = get_user_model().objects.create_user(username='cancel-caller')
        self.recipient = get_user_model().objects.create_user(username='cancel-recipient')
        self.conversation = Conversation.objects.create(created_by=self.caller)
        for user in (self.caller, self.recipient):
            ConversationParticipant.objects.create(conversation=self.conversation, user=user)
        self.client = APIClient()
        self.client.force_authenticate(self.caller)

    def start(self):
        self.client.force_authenticate(self.caller)
        response = self.client.post(f'/api/messaging/conversations/{self.conversation.pk}/calls/start/', {'call_type': 'VOICE'}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data['id']

    def end(self, id, user):
        self.client.force_authenticate(user)
        return self.client.post(f'/api/messaging/calls/{id}/end/')

    def test_cancel_reaches_both_users_without_recipient_call_socket_and_allows_redial(self):
        id = self.start()
        with patch('messaging.call_lifecycle.async_to_sync') as bridge:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.end(id, self.caller)
            self.assertEqual(response.status_code, 200)
            sends = bridge.return_value.call_args_list
            groups = [args.args[0] for args in sends]
            self.assertCountEqual(groups, [f'call_{id}', f'user_{self.caller.pk}', f'user_{self.recipient.pk}'])
            self.assertTrue(all(args.args[1]['call_id'] == id for args in sends))
        self.assertEqual(Call.objects.get(pk=id).status, 'ENDED')
        self.assertEqual(set(CallParticipant.objects.filter(call_id=id).values_list('status', flat=True)), {'LEFT'})
        self.assertFalse(Notification.objects.filter(notification_type='INCOMING_CALL', is_read=False).exists())
        self.client.force_authenticate(self.recipient)
        self.assertEqual(self.client.get('/api/messaging/calls/incoming/').data, [])
        late_accept = self.client.post(f'/api/messaging/calls/{id}/accept/')
        self.assertEqual(late_accept.status_code, 400)
        new_id = self.start()
        self.assertNotEqual(new_id, id)
        self.assertEqual(self.end(id, self.caller).status_code, 200)
        self.assertEqual(self.end(id, self.recipient).status_code, 200)
        self.assertEqual(Call.objects.get(pk=new_id).status, 'RINGING')

    def test_accept_wins_race_then_caller_end_still_finishes_both_users(self):
        id = self.start()
        self.client.force_authenticate(self.recipient)
        self.assertEqual(self.client.post(f'/api/messaging/calls/{id}/accept/').status_code, 200)
        self.assertEqual(self.end(id, self.caller).status_code, 200)
        self.assertEqual(Call.objects.get(pk=id).status, 'ENDED')
        self.assertFalse(CallParticipant.objects.filter(call_id=id, status='JOINED').exists())
        self.start()

    def test_disconnect_before_rest_end_does_not_leave_ringing_call_busy(self):
        id = self.start()
        CallParticipant.objects.filter(call_id=id, user=self.caller).update(status='LEFT')
        self.assertEqual(self.end(id, self.caller).status_code, 200)
        self.start()

    def test_actual_caller_socket_disconnect_finishes_unanswered_call(self):
        id = self.start()
        consumer = CallConsumer()
        consumer.call_id = id
        consumer.user = self.caller
        with self.captureOnCommitCallbacks(execute=True):
            async_to_sync(consumer.mark_participant_left)()
        self.assertEqual(Call.objects.get(pk=id).status, 'ENDED')
        self.assertEqual(CallParticipant.objects.get(call_id=id, user=self.recipient).status, 'LEFT')
        self.assertEqual(self.end(id, self.caller).status_code, 200)
        self.start()

    def test_recipient_decline_finishes_caller_and_allows_immediate_redial(self):
        id = self.start()
        self.client.force_authenticate(self.recipient)
        with self.captureOnCommitCallbacks(execute=True):
            result = self.client.post(f'/api/messaging/calls/{id}/reject/')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(Call.objects.get(pk=id).status, 'ENDED')
        self.assertEqual(CallParticipant.objects.get(call_id=id, user=self.caller).status, 'LEFT')
        self.start()

    def test_outsider_cannot_end_or_accept_call(self):
        id = self.start()
        outsider = get_user_model().objects.create_user(username='cancel-outsider')
        self.assertEqual(self.end(id, outsider).status_code, 403)
        self.assertEqual(self.client.post(f'/api/messaging/calls/{id}/accept/').status_code, 403)
        self.assertEqual(Call.objects.get(pk=id).status, 'RINGING')

    def test_global_user_consumer_forwards_terminal_event(self):
        from unittest.mock import AsyncMock
        consumer = UserConsumer()
        consumer.send = AsyncMock()
        async_to_sync(consumer.call_ended)({'call_id': 42, 'status': 'ENDED', 'ended_by': self.caller.pk})
        self.assertIn('"call_id": 42', consumer.send.call_args.kwargs['text_data'])

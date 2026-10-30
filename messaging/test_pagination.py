from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from .models import Conversation, ConversationParticipant, Message


class MessagePaginationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('message-page-viewer')
        cls.other = get_user_model().objects.create_user('message-page-other')
        cls.conversations = Conversation.objects.bulk_create([Conversation(created_by=cls.user) for _ in range(65)])
        ConversationParticipant.objects.bulk_create([
            ConversationParticipant(conversation=conversation, user=user)
            for conversation in cls.conversations for user in (cls.user, cls.other)
        ])
        Message.objects.bulk_create([Message(conversation=conversation, sender=cls.other, content=f'Body {n}')
                                    for conversation in cls.conversations for n in range(3)])

    def setUp(self):
        self.client = APIClient(); self.client.force_authenticate(self.user)

    def test_conversation_page_batches_latest_messages_and_unread_counts(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get('/api/messaging/conversations/?page_size=2')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)
        self.assertTrue(all(row['last_message']['content'] == 'Body 2' and row['unread_count'] == 3 for row in response.data))
        self.assertLessEqual(len(queries), 8, [query['sql'] for query in queries])
        summary = self.client.get('/api/messaging/conversations/unread-count/')
        self.assertEqual(summary.data['unread_count'], 65 * 3)

    def test_history_starts_with_latest_page_in_chronological_order_and_rechecks_membership(self):
        conversation = self.conversations[0]
        Message.objects.bulk_create([Message(conversation=conversation, sender=self.other, content='More history') for _ in range(60)])
        expected = list(conversation.messages.order_by('pk').values_list('pk', flat=True))
        response = self.client.get(f'/api/messaging/conversations/{conversation.pk}/messages/?page_size=50')
        self.assertEqual([row['id'] for row in response.data], expected[-50:])
        next_url = urlsplit(response['Link'].split('>')[0][1:]); next_path = next_url.path + '?' + next_url.query
        older = self.client.get(next_path)
        self.assertEqual([row['id'] for row in older.data], expected[:-50])
        ConversationParticipant.objects.filter(conversation=conversation, user=self.user).delete()
        self.assertIn(self.client.get(next_path).status_code, (403, 404))
        self.assertEqual(conversation.messages.count(), 63)

    def test_an_older_conversation_with_new_activity_still_moves_to_the_first_page(self):
        from django.utils import timezone
        from datetime import timedelta
        old = self.conversations[0]
        Conversation.objects.filter(pk=old.pk).update(updated_at=timezone.now() + timedelta(seconds=1))
        response = self.client.get('/api/messaging/conversations/?page_size=1')
        self.assertEqual(response.data[0]['id'], old.pk)

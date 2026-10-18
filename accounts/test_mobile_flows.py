from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APITestCase

from accounts.models import UserBlock, ContentReport
from feed.models import Post
from messaging.models import Conversation, ConversationParticipant, Message, Call


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', PASSWORD_RESET_BASE_URL='https://accounts.example.com')
class MobileAccountFlows(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username='mobile-safety', email='member@example.com', password='StrongerPass123!')
        self.other = get_user_model().objects.create_user(username='mobile-other', password='OtherPass123!')
        self.client.force_authenticate(self.user)

    def test_reset_email_and_confirm_single_use(self):
        from rest_framework_simplejwt.tokens import RefreshToken
        old_session = RefreshToken.for_user(self.user)
        self.client.force_authenticate(None)
        response = self.client.post('/api/auth/password-reset/', {'email': self.user.email})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('awinlink://password-reset?', mail.outbox[0].body)
        token = default_token_generator.make_token(self.user)
        data = {'uid': urlsafe_base64_encode(force_bytes(self.user.pk)), 'token': token, 'new_password1': 'ChangedPass567!', 'new_password2': 'ChangedPass567!'}
        self.assertEqual(self.client.post('/api/auth/password-reset/confirm/', data).status_code, 200)
        self.assertEqual(self.client.post('/api/auth/password-reset/confirm/', data).status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('ChangedPass567!'))
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {old_session.access_token}')
        self.assertEqual(self.client.get('/api/auth/me/').status_code, 401)
        self.client.credentials()
        self.assertEqual(self.client.post('/api/auth/refresh/', {'refresh': str(old_session)}).status_code, 401)

    def test_reset_unknown_email_does_not_disclose_membership(self):
        known = self.client.post('/api/auth/password-reset/', {'email': self.user.email})
        unknown = self.client.post('/api/auth/password-reset/', {'email': 'missing@example.com'})
        self.assertEqual(known.data, unknown.data)

    def test_deletion_requires_password_and_deletes_owned_content(self):
        from rest_framework_simplejwt.tokens import RefreshToken
        session = str(RefreshToken.for_user(self.user))
        Post.objects.create(author=self.user, caption='Remove me')
        self.assertEqual(self.client.delete('/api/auth/account/', {'password': 'wrong'}, format='json').status_code, 400)
        self.assertEqual(self.client.delete('/api/auth/account/', {'password': 'StrongerPass123!'}, format='json').status_code, 204)
        self.assertFalse(get_user_model().objects.filter(pk=self.user.pk).exists())
        self.assertFalse(Post.objects.exists())
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post('/api/auth/refresh/', {'refresh': session}).status_code, 401)

    def test_organization_owner_must_transfer_before_deletion(self):
        from organizations.models import Organization
        Organization.objects.create(user=self.user, name='Preserve the team')
        self.assertEqual(self.client.delete('/api/auth/account/', {'password': 'StrongerPass123!'}, format='json').status_code, 409)
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())

    def test_recovery_is_rate_limited(self):
        self.client.force_authenticate(None)
        for _ in range(5):
            self.assertEqual(self.client.post('/api/auth/password-reset/', {'email': 'missing@example.com'}).status_code, 200)
        self.assertEqual(self.client.post('/api/auth/password-reset/', {'email': 'missing@example.com'}).status_code, 429)

    def test_block_prevents_message_call_follow_and_hides_post(self):
        conversation = Conversation.objects.create(created_by=self.user)
        ConversationParticipant.objects.create(conversation=conversation, user=self.user)
        ConversationParticipant.objects.create(conversation=conversation, user=self.other)
        post = Post.objects.create(author=self.other, caption='hidden', visibility='PUBLIC')
        self.assertEqual(self.client.post('/api/safety/blocks/', {'user_id': self.other.pk}).status_code, 200)
        self.assertEqual(self.client.get(f'/api/feed/posts/{post.pk}/').status_code, 403)
        self.assertEqual(self.client.post(f'/api/messaging/conversations/{conversation.pk}/messages/create/', {'message_type': 'TEXT', 'content': 'blocked'}).status_code, 403)
        self.assertEqual(self.client.post(f'/api/messaging/conversations/{conversation.pk}/calls/start/', {'call_type': 'VOICE'}).status_code, 403)
        self.assertEqual(self.client.post(f'/api/follows/users/{self.other.pk}/').status_code, 403)
        self.assertFalse(Message.objects.exists())
        self.assertFalse(Call.objects.exists())
        self.assertEqual(self.client.delete('/api/safety/blocks/', {'user_id': self.other.pk}, format='json').status_code, 204)
        self.assertFalse(UserBlock.objects.exists())

    def test_reports_validate_visibility_and_cannot_read_others_messages(self):
        public = Post.objects.create(author=self.other, caption='report', visibility='PUBLIC')
        private = Post.objects.create(author=self.other, caption='private', visibility='PRIVATE')
        self.assertEqual(self.client.post('/api/safety/reports/', {'target_type': 'post', 'target_id': public.pk, 'reason': 'spam'}).status_code, 201)
        self.assertEqual(self.client.post('/api/safety/reports/', {'target_type': 'post', 'target_id': private.pk, 'reason': 'spam'}).status_code, 404)
        self.assertEqual(ContentReport.objects.count(), 1)

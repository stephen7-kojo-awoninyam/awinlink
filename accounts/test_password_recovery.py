from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.test import Client, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APITestCase

from .recovery import GENERIC_SENT, client_address


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    PASSWORD_RESET_BASE_URL='https://accounts.example.com', PASSWORD_RESET_TIMEOUT=3600,
    PASSWORD_RESET_CACHE_ALIAS='default', PASSWORD_RESET_TRUSTED_PROXY_COUNT=0,
    PASSWORD_RESET_TRUSTED_IP_HEADER='', ALLOWED_HOSTS=['testserver', 'untrusted.example'],
    STORAGES={'default': {'BACKEND': 'django.core.files.storage.InMemoryStorage'},
              'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}},
)
class PasswordRecoveryTests(APITestCase):
    request_url = '/api/auth/password-reset/'
    confirm_url = '/api/auth/password-reset/confirm/'

    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username='recovermember', email='Member@example.com', password='Original!8-Password')
        self.uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        self.token = default_token_generator.make_token(self.user)

    def payload(self, **changes):
        return {'uid': self.uid, 'token': self.token, 'new_password1': 'New!9-PrivatePassword',
                'new_password2': 'New!9-PrivatePassword', **changes}

    def test_registered_email_only_generic_responses(self):
        known = self.client.post(self.request_url, {'email': 'member@EXAMPLE.com'})
        unknown = self.client.post(self.request_url, {'email': 'missing@example.com'})
        username = self.client.post(self.request_url, {'email': self.user.username})
        self.assertEqual(known.status_code, 200)
        self.assertEqual(known.data, unknown.data)
        self.assertEqual(known.data, {'detail': GENERIC_SENT})
        self.assertEqual(username.status_code, 400)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])

    def test_inactive_and_unusable_accounts_receive_no_email(self):
        for active, password in [(False, 'valid'), (True, None)]:
            self.user.is_active = active
            if password is None:
                self.user.set_unusable_password()
            self.user.save()
            result = self.client.post(self.request_url, {'email': self.user.email})
            self.assertEqual(result.data, {'detail': GENERIC_SENT})
        self.assertEqual(len(mail.outbox), 0)

    def test_multipart_email_uses_canonical_origin_not_host(self):
        self.client.post(self.request_url, {'email': self.user.email}, HTTP_HOST='untrusted.example', HTTP_X_FORWARDED_HOST='attacker.example')
        email = mail.outbox[0]
        self.assertEqual(email.content_subtype, 'plain')
        self.assertIn('https://accounts.example.com/accounts/reset/', email.body)
        self.assertIn('awinlink://password-reset?', email.body)
        self.assertIn('60 minutes', email.body)
        self.assertNotIn('untrusted.example', email.body)
        self.assertNotIn('attacker.example', email.body)
        self.assertEqual(email.alternatives[0].mimetype, 'text/html')
        self.assertNotIn(self.token, str(self.client.post(self.request_url, {'email': 'none@example.com'}).data))

    def test_email_failure_is_generic_and_logs_no_secrets(self):
        with patch('accounts.recovery.EmailMultiAlternatives.send', side_effect=RuntimeError('SMTP_PASSWORD_AND_RECIPIENT')):
            with self.assertLogs('accounts.recovery', level='WARNING') as logs:
                result = self.client.post(self.request_url, {'email': self.user.email})
        self.assertEqual(result.data, {'detail': GENERIC_SENT})
        self.assertNotIn('SMTP_PASSWORD_AND_RECIPIENT', str(logs.output))
        self.assertNotIn(self.user.email, str(logs.output))

    def test_request_ip_limit_is_shared_by_web_and_api(self):
        for index in range(5):
            if index % 2:
                self.assertEqual(self.client.post(reverse('password_reset'), {'email': 'missing@example.com'}).status_code, 302)
            else:
                self.assertEqual(self.client.post(self.request_url, {'email': 'missing@example.com'}).status_code, 200)
        response = self.client.post(self.request_url, {'email': 'missing@example.com'}, HTTP_X_FORWARDED_FOR='203.0.113.111')
        self.assertEqual(response.status_code, 429)
        self.assertIn('Retry-After', response)
        self.assertEqual(self.client.post(reverse('password_reset'), {'email': 'missing@example.com'}).status_code, 429)

    def test_email_limit_spans_ips_and_does_not_disclose_membership(self):
        for index in range(5):
            result = self.client.post(self.request_url, {'email': ' MEMBER@EXAMPLE.COM '}, REMOTE_ADDR=f'192.0.2.{index + 1}')
            self.assertEqual(result.data, {'detail': GENERIC_SENT})
        self.assertEqual(len(mail.outbox), 3)

    def test_limiter_failure_fails_closed_before_email(self):
        with patch('accounts.recovery.caches') as caches:
            caches.__getitem__.return_value.add.side_effect = ConnectionError('secret-redis-url')
            with self.assertLogs('accounts.recovery', level='WARNING'):
                result = self.client.post(self.request_url, {'email': self.user.email})
        self.assertEqual(result.status_code, 503)
        self.assertEqual(len(mail.outbox), 0)
        self.assertNotIn('secret-redis-url', str(result.data))

    def test_confirm_is_single_use_and_never_logs_in(self):
        self.assertEqual(self.client.post(self.confirm_url, self.payload()).status_code, 200)
        self.assertEqual(self.client.post(self.confirm_url, self.payload()).status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('New!9-PrivatePassword'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_expiry_is_enforced_by_api_and_web(self):
        with patch.object(default_token_generator, '_now', return_value=datetime.now() - timedelta(seconds=3601)):
            token = default_token_generator.make_token(self.user)
        self.assertEqual(self.client.post(self.confirm_url, self.payload(token=token)).status_code, 400)
        response = self.client.get(reverse('password_reset_confirm', kwargs={'uidb64': self.uid, 'token': token}))
        self.assertContains(response, 'Invalid or expired link')

    def test_modified_token_and_account_cannot_reset(self):
        other = get_user_model().objects.create_user(username='otherrecover', password='Other!9-Password')
        for changes in [{'token': self.token + 'a'}, {'uid': urlsafe_base64_encode(force_bytes(other.pk))}]:
            self.assertEqual(self.client.post(self.confirm_url, self.payload(**changes)).status_code, 400)

    def test_email_and_password_changes_invalidate_old_token(self):
        self.user.email = 'changed@example.com'
        self.user.save()
        self.assertEqual(self.client.post(self.confirm_url, self.payload()).status_code, 400)
        token = default_token_generator.make_token(self.user)
        self.user.set_password('Another!9-NewPassword')
        self.user.save()
        self.assertEqual(self.client.post(self.confirm_url, self.payload(token=token)).status_code, 400)

    def test_disabled_and_unusable_after_issuance_cannot_reset(self):
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.client.post(self.confirm_url, self.payload()).status_code, 400)
        self.user.is_active = True
        self.user.set_unusable_password()
        self.user.save()
        token = default_token_generator.make_token(self.user)
        self.assertEqual(self.client.post(self.confirm_url, self.payload(token=token)).status_code, 400)

    def test_password_policy_mismatch_and_length(self):
        for password in ['123', '1234567890', 'password', self.user.username, 'x' * 4097]:
            response = self.client.post(self.confirm_url, self.payload(new_password1=password, new_password2=password))
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post(self.confirm_url, self.payload(new_password2='Different!9')).status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Original!8-Password'))

    def test_malformed_payloads_do_not_crash(self):
        for payload in [[], {'uid': []}, self.payload(uid={'x': 1}), self.payload(token=None), self.payload(uid='a' * 65), self.payload(token='a' * 129), self.payload(new_password1=['array'])]:
            self.assertEqual(self.client.post(self.confirm_url, payload, format='json').status_code, 400)
        self.assertEqual(self.client.post(self.request_url, [], format='json').status_code, 400)

    def test_confirmation_rate_limit_and_security_headers(self):
        for _ in range(20):
            self.assertEqual(self.client.post(self.confirm_url, self.payload(token='bad')).status_code, 400)
        result = self.client.post(self.confirm_url, self.payload())
        self.assertEqual(result.status_code, 429)
        self.assertEqual(result['Referrer-Policy'], 'no-referrer')
        self.assertIn('no-store', result['Cache-Control'])

    def test_web_end_to_end_and_cross_channel_replay(self):
        response = self.client.post(reverse('password_reset'), {'email': self.user.email})
        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertIn('https://accounts.example.com', mail.outbox[0].body)
        path = reverse('password_reset_confirm', kwargs={'uidb64': self.uid, 'token': self.token})
        landing = self.client.get(path)
        self.assertEqual(landing.status_code, 302)
        self.assertNotIn(self.token, landing.url)
        self.assertEqual(landing['Referrer-Policy'], 'no-referrer')
        self.assertContains(self.client.get(landing.url), 'at least 8 characters')
        invalid = self.client.post(landing.url, self.payload(new_password1='weak', new_password2='weak'))
        self.assertEqual(invalid.status_code, 200)
        completed = self.client.post(landing.url, self.payload())
        self.assertRedirects(completed, reverse('password_reset_complete'))
        self.assertEqual(self.client.post(self.confirm_url, self.payload()).status_code, 400)
        self.assertNotIn('_password_reset_token', self.client.session)

    def test_web_csrf_required(self):
        browser = Client(enforce_csrf_checks=True)
        self.assertEqual(browser.post(reverse('password_reset'), {'email': self.user.email}).status_code, 403)

    def test_proxy_headers_require_explicit_trust(self):
        from django.test import RequestFactory
        request = RequestFactory().get('/', REMOTE_ADDR='127.0.0.1', HTTP_X_FORWARDED_FOR='203.0.113.1', HTTP_X_REAL_IP='203.0.113.2')
        self.assertEqual(client_address(request), '127.0.0.1')
        with override_settings(PASSWORD_RESET_TRUSTED_IP_HEADER='HTTP_X_REAL_IP'):
            self.assertEqual(client_address(request), '203.0.113.2')

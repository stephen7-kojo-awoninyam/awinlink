from io import BytesIO, StringIO
import json
import re
import ssl
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APITestCase

from config.email_settings import email_settings, RESEND_BACKEND
from .email_backends.resend import EmailBackend, ENDPOINT, NoRedirect, ResendDeliveryError
from .email_configuration import inspect_email_configuration
from . import test_password_recovery as fixtures

VALID = {
    'EMAIL_BACKEND': RESEND_BACKEND, 'RESEND_API_KEY': 're_synthetic_key_not_real', 'RESEND_TIMEOUT': 10,
    'DEFAULT_FROM_EMAIL': 'Awinlink <recovery@notifications.awinlink.com>',
    'EMAIL_FROM_EXPLICIT': True, 'EMAIL_SENDER_DOMAIN': 'notifications.awinlink.com',
    'PASSWORD_RESET_BASE_URL': 'https://awinlink.com', 'PASSWORD_RESET_TIMEOUT': 3600,
}


def accepted_response():
    response = MagicMock()
    response.status = 200
    response.read.return_value = b'{"id":"synthetic-provider-id"}'
    context = MagicMock()
    context.__enter__.return_value = response
    return context, response


class ResendSelectionTests(SimpleTestCase):
    def test_resend_is_explicit_and_smtp_values_are_not_required(self):
        config = email_settings({'EMAIL_PROVIDER': 'resend', 'RESEND_API_KEY': 're_synthetic_key',
            'EMAIL_USE_TLS': 'unused-invalid-value', 'EMAIL_USE_SSL': 'true'}, production=True)
        self.assertEqual(config['EMAIL_BACKEND'], RESEND_BACKEND)
        self.assertNotIn('EMAIL_HOST_PASSWORD', config)
        self.assertEqual(config['RESEND_TIMEOUT'], 10)

    def test_key_presence_alone_does_not_enable_sending(self):
        config = email_settings({'RESEND_API_KEY': 're_synthetic_key'}, production=False)
        self.assertEqual(config['EMAIL_BACKEND'], 'django.core.mail.backends.console.EmailBackend')

    def test_invalid_provider_and_timeout_are_redacted(self):
        from django.core.exceptions import ImproperlyConfigured
        for changes in [{'EMAIL_PROVIDER': 'private-secret'},
                        {'EMAIL_PROVIDER': 'resend', 'RESEND_TIMEOUT': 'private-secret'},
                        {'EMAIL_PROVIDER': 'resend', 'RESEND_TIMEOUT': '0'},
                        {'EMAIL_PROVIDER': 'resend', 'RESEND_TIMEOUT': '61'}]:
            with self.assertRaises(ImproperlyConfigured) as error:
                email_settings(changes, production=True)
            self.assertNotIn('private-secret', str(error.exception))


@override_settings(**VALID)
class ResendBackendTests(SimpleTestCase):
    def setUp(self):
        guard = patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('Real HTTP forbidden in tests'))
        guard.start(); self.addCleanup(guard.stop)
        opener_patch = patch('accounts.email_backends.resend.build_opener')
        self.factory = opener_patch.start(); self.addCleanup(opener_patch.stop)
        self.opener = self.factory.return_value
        self.context, self.response = accepted_response()
        self.opener.open.return_value = self.context

    def message(self, **kwargs):
        message = EmailMultiAlternatives('Reset your password', 'Existing text body', VALID['DEFAULT_FROM_EMAIL'],
            ['member@example.com'], **kwargs)
        message.attach_alternative('<p>Existing HTML body</p>', 'text/html')
        return message

    def test_existing_multipart_content_uses_fixed_https_endpoint_and_bearer_auth(self):
        message = self.message()
        self.assertEqual(EmailBackend().send_messages([message]), 1)
        request = self.opener.open.call_args.args[0]
        self.assertEqual(request.full_url, 'https://api.resend.com/emails')
        self.assertEqual(request.method, 'POST')
        self.assertEqual(request.get_header('Authorization'), 'Bearer ' + VALID['RESEND_API_KEY'])
        self.assertEqual(self.opener.open.call_args.kwargs['timeout'], 10)
        payload = json.loads(request.data)
        self.assertEqual(payload['text'], message.body)
        self.assertEqual(payload['html'], message.alternatives[0].content)
        self.assertEqual(payload['to'], message.to)
        self.assertEqual(payload['from'], message.from_email)

    def test_tls_verification_no_proxies_and_redirect_refusal(self):
        EmailBackend().send_messages([self.message()])
        proxy, https, redirects = self.factory.call_args.args
        self.assertEqual(proxy.proxies, {})
        self.assertTrue(https._context.check_hostname)
        self.assertEqual(https._context.verify_mode, ssl.CERT_REQUIRED)
        self.assertEqual(https._context.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertIsInstance(redirects, NoRedirect)
        self.assertIsNone(redirects.redirect_request(None, None, 302, '', {}, 'https://attacker.invalid'))

    def test_idempotency_key_stays_with_message_and_contains_no_recipient_or_token(self):
        message = self.message()
        backend = EmailBackend()
        backend.send_messages([message]); backend.send_messages([message])
        keys = [call.args[0].get_header('Idempotency-key') for call in self.opener.open.call_args_list]
        self.assertEqual(keys[0], keys[1])
        self.assertTrue(keys[0].startswith('awinlink-email/'))
        self.assertNotIn('member', keys[0])

    def test_cc_bcc_reply_to_headers_and_attachments_are_preserved(self):
        message = self.message(cc=['cc@example.com'], bcc=['hidden@example.com'], reply_to=['support@example.com'],
            headers={'X-Awinlink-Type': 'recovery'})
        message.attach('note.txt', 'attachment text', 'text/plain')
        EmailBackend().send_messages([message])
        payload = json.loads(self.opener.open.call_args.args[0].data)
        self.assertEqual(payload['bcc'], ['hidden@example.com'])
        self.assertNotIn('Bcc', payload['headers'])
        self.assertEqual(payload['reply_to'], ['support@example.com'])
        self.assertEqual(payload['attachments'][0]['content'], 'YXR0YWNobWVudCB0ZXh0')

    def test_header_injection_and_envelope_overrides_are_refused_before_network(self):
        for message in [self.message(), self.message(headers={'Bcc': 'leak@example.com'})]:
            if not message.extra_headers:
                message.subject = 'Reset\r\nBcc: attacker@example.com'
            with self.assertRaises(ResendDeliveryError):
                EmailBackend().send_messages([message])
        self.opener.open.assert_not_called()

    def test_invalid_key_and_timeout_are_refused_without_network(self):
        for changes in [{'RESEND_API_KEY': ''}, {'RESEND_API_KEY': 're_private\r\nInjected: value'}, {'RESEND_TIMEOUT': 0}]:
            with override_settings(**changes), self.assertRaises(ResendDeliveryError) as error:
                EmailBackend().send_messages([self.message()])
            self.assertNotIn('private', str(error.exception))
        self.opener.open.assert_not_called()

    def test_provider_errors_and_timeout_do_not_expose_content_or_retry(self):
        for failure in [TimeoutError('private-token-and-key'),
                        HTTPError(ENDPOINT, 403, 'private-token-and-key', {}, BytesIO(b'private-token-and-key')),
                        ssl.SSLError('private-token-and-key')]:
            self.opener.open.reset_mock()
            self.opener.open.side_effect = failure
            with self.assertRaises(ResendDeliveryError) as error:
                EmailBackend().send_messages([self.message()])
            self.assertNotIn('private-token-and-key', str(error.exception))
            self.opener.open.assert_called_once()

    def test_invalid_or_unbounded_provider_response_is_not_success(self):
        for body in [b'not-json', b'{}', b'{"id": null}', b'x' * 65537]:
            self.response.read.return_value = body
            with self.assertRaises(ResendDeliveryError):
                EmailBackend().send_messages([self.message()])

    def test_non_success_http_status_is_not_success(self):
        self.response.status = 429
        with self.assertRaises(ResendDeliveryError):
            EmailBackend().send_messages([self.message()])
        self.response.read.assert_not_called()

    def test_silent_failure_and_empty_message_batch_return_zero(self):
        self.opener.open.side_effect = OSError('private')
        self.assertEqual(EmailBackend(fail_silently=True).send_messages([self.message()]), 0)
        self.assertEqual(EmailBackend().send_messages([]), 0)
        empty = self.message(); empty.to = []
        self.assertEqual(EmailBackend().send_messages([empty]), 0)


@override_settings(**VALID)
class ResendReadinessTests(SimpleTestCase):
    def test_resend_does_not_require_smtp_settings(self):
        report = inspect_email_configuration(SimpleNamespace(**VALID))
        self.assertTrue(report['configuration_valid'])
        self.assertEqual(report['transport'], 'https_api')
        self.assertNotIn(VALID['RESEND_API_KEY'], json.dumps(report))
        self.assertEqual(report['sender_authorization'], 'not_verified_with_provider')

    def test_missing_key_and_unapproved_sender_configuration_fail_safely(self):
        for changes in [{'RESEND_API_KEY': ''}, {'RESEND_TIMEOUT': None},
                        {'EMAIL_SENDER_DOMAIN': 'other.com'}, {'EMAIL_FROM_EXPLICIT': False},
                        {'DEFAULT_FROM_EMAIL': 'onboarding@resend.dev', 'EMAIL_SENDER_DOMAIN': 'resend.dev'}]:
            report = inspect_email_configuration(SimpleNamespace(**{**VALID, **changes}))
            self.assertFalse(report['configuration_valid'])
            self.assertNotIn(VALID['RESEND_API_KEY'], json.dumps(report))

    def test_offline_command_does_not_send_connect_resolve_or_read_accounts(self):
        output = StringIO()
        with patch('accounts.email_backends.resend.build_opener') as opener, patch('socket.create_connection') as network, \
             patch('socket.getfqdn') as dns, patch('smtplib.SMTP') as smtp, \
             patch('django.core.mail.message.EmailMessage.send') as send:
            call_command('check_email_delivery', '--json', stdout=output)
        for mock in [opener, network, dns, smtp, send]:
            mock.assert_not_called()
        report = json.loads(output.getvalue())
        self.assertTrue(report['configuration_valid'])
        self.assertEqual(report['provider'], 'resend')
        self.assertEqual(report['emails_sent'], 0)

    def test_smtp_probe_is_refused_for_resend_without_fallback(self):
        output = StringIO()
        with patch('accounts.email_backends.resend.build_opener') as opener, patch('smtplib.SMTP') as smtp, self.assertRaises(CommandError):
            call_command('check_email_delivery', '--smtp-handshake', '--json', stdout=output)
        opener.assert_not_called(); smtp.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())['smtp_probe']['status'], 'not_supported_for_resend')


@override_settings(**{**fixtures.PasswordRecoveryTests._overridden_settings, **VALID})
class ResendRecoveryIntegrationTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username='resend-member', email='resend-member@example.com', password='Original!9-Password')
        guard = patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('Real HTTP forbidden in tests'))
        guard.start(); self.addCleanup(guard.stop)
        opener_patch = patch('accounts.email_backends.resend.build_opener')
        self.opener = opener_patch.start().return_value; self.addCleanup(opener_patch.stop)
        self.opener.open.return_value = accepted_response()[0]

    def test_api_reset_uses_existing_templates_and_django_single_use_tokens(self):
        result = self.client.post('/api/auth/password-reset/', {'email': self.user.email})
        self.assertEqual(result.status_code, 200)
        payload = json.loads(self.opener.open.call_args.args[0].data)
        self.assertIn('awinlink://password-reset?', payload['text'])
        self.assertIn('60 minutes', payload['text'])
        self.assertIn('Reset My Password', payload['html'])
        uid, token = re.search(r'/accounts/reset/([^/]+)/([^/]+)/', payload['text']).groups()
        data = {'uid': uid, 'token': token, 'new_password1': 'Changed!9-NewPassword', 'new_password2': 'Changed!9-NewPassword'}
        self.assertEqual(self.client.post('/api/auth/password-reset/confirm/', data).status_code, 200)
        self.assertEqual(self.client.post('/api/auth/password-reset/confirm/', data).status_code, 400)

    def test_web_uses_same_backend_and_unknown_accounts_do_not_call_provider(self):
        response = self.client.post('/accounts/password-reset/', {'email': self.user.email})
        self.assertEqual(response.status_code, 302)
        self.opener.open.assert_called_once()
        unknown = self.client.post('/accounts/password-reset/', {'email': 'unknown@example.com'})
        self.assertEqual(unknown.status_code, response.status_code)
        self.assertEqual(unknown.url, response.url)
        self.opener.open.assert_called_once()

    def test_resend_failure_preserves_generic_response_and_secret_free_warning(self):
        self.opener.open.side_effect = HTTPError(ENDPOINT, 403, 'secret-token-and-api-key', {}, BytesIO(b'secret-token-and-api-key'))
        with self.assertLogs('accounts.recovery', level='WARNING') as logs:
            known = self.client.post('/api/auth/password-reset/', {'email': self.user.email})
        unknown = self.client.post('/api/auth/password-reset/', {'email': 'unknown@example.com'})
        self.assertEqual(known.data, unknown.data)
        self.assertNotIn('secret-token-and-api-key', str(logs.output))
        self.assertNotIn(self.user.email, str(logs.output))
        self.assertEqual(known.status_code, 200)

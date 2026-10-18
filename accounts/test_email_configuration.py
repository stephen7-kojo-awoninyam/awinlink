from io import StringIO
import json
import smtplib
import ssl
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from config.email_settings import smtp_settings
from .email_configuration import inspect_email_configuration, probe_smtp_without_sending


VALID = {
    'EMAIL_BACKEND': 'django.core.mail.backends.smtp.EmailBackend',
    'EMAIL_HOST': 'smtp.postmarkapp.com', 'EMAIL_PORT': 587,
    'EMAIL_HOST_USER': 'synthetic-user-do-not-print',
    'EMAIL_HOST_PASSWORD': 'synthetic-password-do-not-print',
    'EMAIL_USE_TLS': True, 'EMAIL_USE_SSL': False, 'EMAIL_TIMEOUT': 10,
    'DEFAULT_FROM_EMAIL': 'Awinlink <recovery@notifications.awinlink.com>',
    'EMAIL_FROM_EXPLICIT': True, 'EMAIL_SENDER_DOMAIN': 'notifications.awinlink.com',
    'PASSWORD_RESET_BASE_URL': 'https://awinlink.com', 'PASSWORD_RESET_TIMEOUT': 3600,
}


class SMTPSettingsTests(SimpleTestCase):
    def test_secure_defaults_and_explicit_sender(self):
        config = smtp_settings({})
        self.assertTrue(config['EMAIL_USE_TLS'])
        self.assertFalse(config['EMAIL_USE_SSL'])
        self.assertEqual(config['EMAIL_PORT'], 587)
        self.assertFalse(config['EMAIL_FROM_EXPLICIT'])
        self.assertEqual(smtp_settings({'EMAIL_USE_SSL': 'true'})['EMAIL_PORT'], 465)

    def test_conflicting_tls_flags_rejected(self):
        with self.assertRaises(ImproperlyConfigured):
            smtp_settings({'EMAIL_USE_SSL': 'true', 'EMAIL_USE_TLS': 'true'})

    def test_invalid_environment_values_do_not_echo_input(self):
        for name in ['EMAIL_USE_TLS', 'EMAIL_USE_SSL', 'EMAIL_PORT', 'EMAIL_TIMEOUT']:
            with self.subTest(name=name), self.assertRaises(ImproperlyConfigured) as error:
                smtp_settings({name: 'synthetic-password-do-not-print'})
            self.assertNotIn('synthetic-password-do-not-print', str(error.exception))

    def test_invalid_timeout_and_port_rejected(self):
        for env in [{'EMAIL_TIMEOUT': '0'}, {'EMAIL_TIMEOUT': '61'}, {'EMAIL_PORT': '65536'}]:
            with self.assertRaises(ImproperlyConfigured):
                smtp_settings(env)


@override_settings(**VALID)
class EmailReadinessTests(SimpleTestCase):
    def config(self, **changes):
        return SimpleNamespace(**{**VALID, **changes})

    def test_postmark_transactional_configuration(self):
        report = inspect_email_configuration(settings)
        self.assertTrue(report['configuration_valid'])
        self.assertEqual(report['provider'], 'postmark')
        self.assertEqual(report['sender_authorization'], 'not_verified_with_provider')
        self.assertEqual(report['emails_sent'], 0)

    def test_provider_neutral_implicit_tls(self):
        report = inspect_email_configuration(self.config(EMAIL_HOST='smtp.provider.com', EMAIL_USE_TLS=False, EMAIL_USE_SSL=True, EMAIL_PORT=465))
        self.assertTrue(report['configuration_valid'])

    def test_insecure_and_conflicting_tls_are_rejected(self):
        for tls, implicit in [(False, False), (True, True)]:
            report = inspect_email_configuration(self.config(EMAIL_USE_TLS=tls, EMAIL_USE_SSL=implicit))
            self.assertFalse(report['configuration_valid'])

    def test_postmark_broadcast_host_and_465_are_rejected(self):
        for changes in [{'EMAIL_HOST': 'smtp-broadcasts.postmarkapp.com'},
                        {'EMAIL_PORT': 465, 'EMAIL_USE_TLS': False, 'EMAIL_USE_SSL': True}]:
            report = inspect_email_configuration(self.config(**changes))
            self.assertIn('postmark_transactional', [i['code'] for i in report['issues']])

    def test_missing_credentials_do_not_echo_configured_values(self):
        for changes in [{'EMAIL_HOST_USER': ''}, {'EMAIL_HOST_PASSWORD': ''}]:
            report = inspect_email_configuration(self.config(**changes))
            self.assertFalse(report['configuration_valid'])
            self.assertNotIn(VALID['EMAIL_HOST_USER'], json.dumps(report))
            self.assertNotIn(VALID['EMAIL_HOST_PASSWORD'], json.dumps(report))

    def test_sender_header_injection_multiple_addresses_and_placeholder(self):
        for sender in ['Awinlink <one@awinlink.com>\r\nBcc: two@awinlink.com',
                       'one@awinlink.com,two@awinlink.com', 'not-an-address', 'one@example.invalid']:
            report = inspect_email_configuration(self.config(DEFAULT_FROM_EMAIL=sender))
            self.assertFalse(report['sender_syntax_valid'])

    def test_sender_domain_and_explicit_sender_required(self):
        for changes in [{'EMAIL_SENDER_DOMAIN': ''}, {'EMAIL_SENDER_DOMAIN': 'other.com'}, {'EMAIL_FROM_EXPLICIT': False}]:
            self.assertFalse(inspect_email_configuration(self.config(**changes))['configuration_valid'])

    def test_unsafe_origin_and_host_never_echoed(self):
        for changes in [{'PASSWORD_RESET_BASE_URL': 'http://awinlink.com'},
                        {'PASSWORD_RESET_BASE_URL': 'https://user:secret@awinlink.com'},
                        {'PASSWORD_RESET_BASE_URL': 'https://awinlink.com/path'},
                        {'EMAIL_HOST': 'smtp://user:secret@smtp.provider.com'}]:
            report = inspect_email_configuration(self.config(**changes))
            self.assertFalse(report['configuration_valid'])
            self.assertNotIn('user:secret', json.dumps(report))

    def test_default_command_is_offline_and_does_not_send_or_resolve_dns(self):
        output = StringIO()
        with patch('smtplib.SMTP') as smtp, patch('smtplib.SMTP_SSL') as smtps, \
             patch('django.core.mail.message.EmailMessage.send') as send, \
             patch('socket.getfqdn') as dns, patch('socket.create_connection') as connect:
            call_command('check_email_delivery', '--json', stdout=output)
        smtp.assert_not_called(); smtps.assert_not_called(); send.assert_not_called()
        dns.assert_not_called(); connect.assert_not_called()
        report = json.loads(output.getvalue())
        self.assertTrue(report['configuration_valid'])
        self.assertEqual(report['template_render'], 'passed')
        self.assertEqual(report['smtp_probe']['status'], 'not_run')
        self.assertNotIn(VALID['EMAIL_HOST_PASSWORD'], output.getvalue())

    def test_invalid_config_fails_without_network_even_with_handshake_flag(self):
        output = StringIO()
        with override_settings(EMAIL_HOST_PASSWORD=''), patch('smtplib.SMTP') as smtp, \
             self.assertRaises(CommandError):
            call_command('check_email_delivery', '--smtp-handshake', '--json', stdout=output)
        smtp.assert_not_called()
        self.assertFalse(json.loads(output.getvalue())['configuration_valid'])

    def test_template_failure_is_redacted(self):
        output = StringIO()
        with patch('accounts.management.commands.check_email_delivery.render_to_string', side_effect=RuntimeError(VALID['EMAIL_HOST_PASSWORD'])), self.assertRaises(CommandError):
            call_command('check_email_delivery', '--json', stdout=output)
        self.assertNotIn(VALID['EMAIL_HOST_PASSWORD'], output.getvalue())
        self.assertEqual(json.loads(output.getvalue())['template_render'], 'failed')

    def test_handshake_uses_verified_tls_before_auth_and_never_submits_mail(self):
        with patch('smtplib.SMTP') as smtp:
            client = smtp.return_value
            client.ehlo.return_value = (250, b'OK')
            client.has_extn.return_value = True
            client.noop.return_value = (250, b'OK')
            result = probe_smtp_without_sending(settings)
        self.assertEqual(result['status'], 'tls_and_authentication_passed')
        context = client.starttls.call_args.kwargs['context']
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        methods = [call[0] for call in client.method_calls]
        self.assertLess(methods.index('starttls'), methods.index('login'))
        for method in ['sendmail', 'send_message', 'mail', 'rcpt', 'data', 'verify']:
            getattr(client, method).assert_not_called()
        client.quit.assert_called_once()

    def test_no_starttls_means_no_authentication_or_send(self):
        with patch('smtplib.SMTP') as smtp:
            client = smtp.return_value
            client.ehlo.return_value = (250, b'OK')
            client.has_extn.return_value = False
            result = probe_smtp_without_sending(settings)
        self.assertEqual(result['status'], 'starttls_not_supported')
        client.login.assert_not_called()
        client.sendmail.assert_not_called()

    def test_smtp_failures_are_redacted(self):
        for failure, expected in [(smtplib.SMTPAuthenticationError(535, VALID['EMAIL_HOST_PASSWORD'].encode()), 'authentication_failed'),
                                  (ssl.SSLError(VALID['EMAIL_HOST_PASSWORD']), 'tls_verification_failed'),
                                  (OSError(VALID['EMAIL_HOST_PASSWORD']), 'connection_failed')]:
            with patch('smtplib.SMTP', side_effect=failure):
                result = probe_smtp_without_sending(settings)
            self.assertEqual(result['status'], expected)
            self.assertNotIn(VALID['EMAIL_HOST_PASSWORD'], json.dumps(result))

    def test_implicit_tls_context_is_verified_and_starttls_not_used(self):
        config = self.config(EMAIL_HOST='smtp.provider.com', EMAIL_PORT=465, EMAIL_USE_SSL=True, EMAIL_USE_TLS=False)
        with patch('smtplib.SMTP_SSL') as smtp:
            client = smtp.return_value
            client.ehlo.return_value = (250, b'OK')
            client.noop.return_value = (250, b'OK')
            result = probe_smtp_without_sending(config)
        self.assertEqual(result['status'], 'tls_and_authentication_passed')
        self.assertTrue(smtp.call_args.kwargs['context'].check_hostname)
        client.starttls.assert_not_called()
        client.sendmail.assert_not_called()

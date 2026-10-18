import json
from types import SimpleNamespace
from urllib.parse import urlsplit

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand, CommandError
from django.template.loader import render_to_string

from accounts.email_configuration import inspect_email_configuration, probe_smtp_without_sending


class Command(BaseCommand):
    help = 'Check SMTP/Resend recovery readiness offline without sending email. --smtp-handshake is SMTP-only.'
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument('--smtp-handshake', action='store_true', help='Connect and authenticate over TLS; never submit any message.')
        parser.add_argument('--json', action='store_true', help='Emit only secret-free JSON status.')

    def handle(self, *args, **options):
        report = inspect_email_configuration(settings)
        report['mode'] = 'smtp_handshake_no_send' if options['smtp_handshake'] else 'offline_no_send'
        # Render dummy content and build MIME in memory. Never generate a real
        # account token, read a user, call message.send(), or open a mail backend.
        try:
            origin = urlsplit(settings.PASSWORD_RESET_BASE_URL)
            context = {'protocol': 'https', 'domain': origin.netloc,
                       'user': SimpleNamespace(get_username=lambda: 'delivery-check'),
                       'uid': 'NOTANACCOUNT', 'token': 'not-a-real-reset-token',
                       'expiry_minutes': settings.PASSWORD_RESET_TIMEOUT // 60, 'mobile': True}
            subject = ''.join(render_to_string('accounts/password_reset_subject.txt', context).splitlines())
            plain = render_to_string('accounts/password_reset_email.txt', context)
            html = render_to_string('accounts/password_reset_email.html', context)
            message = EmailMultiAlternatives(subject, plain, settings.DEFAULT_FROM_EMAIL, ['nobody@example.invalid'],
                headers={'Message-ID': '<offline-delivery-check@example.invalid>'})
            message.attach_alternative(html, 'text/html')
            message.message()
            report['template_render'] = 'passed'
        except Exception:
            report['template_render'] = 'failed'
            report['configuration_valid'] = False
            report['issues'].append({'code': 'templates', 'message': 'Recovery email templates or MIME headers failed validation; details withheld.'})
        report['smtp_probe'] = {'status': 'not_run', 'emails_sent': 0}
        if options['smtp_handshake'] and report['configuration_valid']:
            report['smtp_probe'] = probe_smtp_without_sending(settings)
        if options['json']:
            self.stdout.write(json.dumps(report, sort_keys=True))
        else:
            self.stdout.write('Email configuration: ' + ('PASS' if report['configuration_valid'] else 'NOT READY'))
            for issue in report['issues']:
                self.stdout.write(f"{issue['code']}: {issue['message']}")
            self.stdout.write('Template/MIME validation: ' + report['template_render'])
            self.stdout.write('SMTP probe: ' + report['smtp_probe']['status'])
            self.stdout.write('No email sent. Provider sender authorization and inbox delivery remain unverified.')
        if not report['configuration_valid'] or (options['smtp_handshake'] and report['smtp_probe']['status'] != 'tls_and_authentication_passed'):
            raise CommandError('Email readiness check did not pass. No email was sent.')

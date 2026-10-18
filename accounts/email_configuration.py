"""Secret-free SMTP/Resend readiness checks. No mail is submitted here."""
from email.utils import getaddresses
import re
import smtplib
import ssl
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

SMTP_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
RESEND_BACKEND = 'accounts.email_backends.resend.EmailBackend'


def inspect_email_configuration(config):
    issues = []
    def issue(code, message):
        issues.append({'code': code, 'message': message})

    if getattr(config, 'EMAIL_BACKEND', '') == RESEND_BACKEND:
        key = getattr(config, 'RESEND_API_KEY', '')
        if not isinstance(key, str) or not re.fullmatch(r're_[A-Za-z0-9_-]+', key):
            issue('resend_key', 'Set RESEND_API_KEY to a provider-issued sending key; value withheld.')
        timeout = getattr(config, 'RESEND_TIMEOUT', None)
        if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 60:
            issue('resend_timeout', 'RESEND_TIMEOUT must be between 1 and 60 seconds.')
        transport = {'provider': 'resend', 'tls_mode': 'https', 'transport': 'https_api'}
    else:
        transport, smtp_issues = inspect_smtp_configuration(config)
        issues.extend(smtp_issues)

    sender = getattr(config, 'DEFAULT_FROM_EMAIL', '')
    sender_valid = False
    sender_domain = ''
    try:
        if not isinstance(sender, str) or '\r' in sender or '\n' in sender:
            raise ValueError
        addresses = getaddresses([sender])
        if len(addresses) != 1:
            raise ValueError
        address = addresses[0][1]
        validate_email(address)
        sender_domain = address.rsplit('@', 1)[1].lower()
        if sender_domain in ('localhost', 'example.com', 'example.net', 'example.org') or sender_domain.endswith(('.invalid', '.test', '.example', '.localhost')):
            raise ValueError
        sender_valid = True
    except (ValueError, TypeError, ValidationError):
        issue('sender_address', 'DEFAULT_FROM_EMAIL must contain one real sender mailbox, without header injection or placeholders.')
    if not getattr(config, 'EMAIL_FROM_EXPLICIT', False):
        issue('sender_explicit', 'Set DEFAULT_FROM_EMAIL explicitly; a code fallback is not proof of provider authorization.')
    expected_domain = getattr(config, 'EMAIL_SENDER_DOMAIN', '')
    if not expected_domain:
        issue('sender_domain', 'Set EMAIL_SENDER_DOMAIN to the exact domain of the provider-approved From address.')
    elif not sender_valid or sender_domain != expected_domain.lower():
        issue('sender_domain_match', 'DEFAULT_FROM_EMAIL must match EMAIL_SENDER_DOMAIN.')
    if transport['provider'] == 'resend' and sender_domain == 'resend.dev':
        issue('resend_test_sender', 'Use your verified sending domain for recovery, not the Resend onboarding domain.')
    try:
        origin = urlsplit(getattr(config, 'PASSWORD_RESET_BASE_URL', ''))
        if (origin.scheme != 'https' or not origin.hostname or origin.username or origin.password
                or origin.path not in ('', '/') or origin.query or origin.fragment):
            raise ValueError
    except (TypeError, ValueError):
        issue('reset_origin', 'PASSWORD_RESET_BASE_URL must be a canonical HTTPS origin without credentials, path or query.')
    return {'configuration_valid': not issues, 'issues': issues, **transport,
            'sender_syntax_valid': sender_valid,
            'sender_domain_matches': bool(sender_valid and expected_domain and sender_domain == expected_domain.lower()),
            'sender_authorization': 'not_verified_with_provider',
            'inbox_delivery': 'not_tested', 'emails_sent': 0}


def inspect_smtp_configuration(config):
    issues = []
    def issue(code, message):
        issues.append({'code': code, 'message': message})
    host = getattr(config, 'EMAIL_HOST', '')
    host_valid = bool(isinstance(host, str) and len(host) <= 253 and re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?', host))
    if not host_valid:
        issue('smtp_host', 'EMAIL_HOST must contain a provider hostname, without URL credentials or a port.')
    if getattr(config, 'EMAIL_BACKEND', '') != SMTP_BACKEND:
        issue('smtp_backend', 'Production recovery must use the Django SMTP email backend.')
    if not getattr(config, 'EMAIL_HOST_USER', '').strip():
        issue('smtp_username', 'EMAIL_HOST_USER is required for authenticated transactional SMTP.')
    if not getattr(config, 'EMAIL_HOST_PASSWORD', ''):
        issue('smtp_password', 'EMAIL_HOST_PASSWORD is required for authenticated transactional SMTP.')
    tls, implicit = getattr(config, 'EMAIL_USE_TLS', False), getattr(config, 'EMAIL_USE_SSL', False)
    if not isinstance(tls, bool) or not isinstance(implicit, bool) or tls == implicit:
        issue('tls_mode', 'Enable exactly one of EMAIL_USE_TLS or EMAIL_USE_SSL.')
    port = getattr(config, 'EMAIL_PORT', None)
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        issue('smtp_port', 'EMAIL_PORT must be a valid numeric SMTP port.')
    elif (tls and port == 465) or (implicit and port in (25, 587, 2525)):
        issue('tls_port', 'EMAIL_PORT does not match the configured SMTP TLS mode.')
    timeout = getattr(config, 'EMAIL_TIMEOUT', None)
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not 1 <= timeout <= 60:
        issue('smtp_timeout', 'EMAIL_TIMEOUT must be bounded between 1 and 60 seconds.')
    postmark = isinstance(host, str) and host.lower().endswith('postmarkapp.com')
    if postmark and (host.lower() != 'smtp.postmarkapp.com' or not tls or implicit or port not in (587, 2525)):
        issue('postmark_transactional', 'Postmark recovery requires its transactional SMTP host and STARTTLS on port 587 or 2525.')

    return {'provider': 'postmark' if postmark else 'custom_smtp', 'transport': 'smtp',
            'tls_mode': 'starttls' if tls and not implicit else 'implicit_tls' if implicit and not tls else 'invalid'}, issues


def probe_smtp_without_sending(config):
    """Optional EHLO/TLS/AUTH/NOOP/QUIT only. Never MAIL/RCPT/DATA or sendmail."""
    if getattr(config, 'EMAIL_BACKEND', '') == RESEND_BACKEND:
        return {'status': 'not_supported_for_resend', 'emails_sent': 0}
    if not inspect_email_configuration(config)['configuration_valid']:
        return {'status': 'refused_invalid_configuration', 'emails_sent': 0}
    client = None
    try:
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        if config.EMAIL_USE_SSL:
            client = smtplib.SMTP_SSL(config.EMAIL_HOST, config.EMAIL_PORT,
                                      timeout=config.EMAIL_TIMEOUT, context=context)
        else:
            client = smtplib.SMTP(config.EMAIL_HOST, config.EMAIL_PORT, timeout=config.EMAIL_TIMEOUT)
        client.set_debuglevel(0)
        code, _ = client.ehlo()
        if code != 250:
            return {'status': 'smtp_greeting_failed', 'emails_sent': 0}
        if config.EMAIL_USE_TLS:
            if not client.has_extn('starttls'):
                return {'status': 'starttls_not_supported', 'emails_sent': 0}
            client.starttls(context=context)
            code, _ = client.ehlo()
            if code != 250:
                return {'status': 'encrypted_greeting_failed', 'emails_sent': 0}
        client.login(config.EMAIL_HOST_USER, config.EMAIL_HOST_PASSWORD)
        code, _ = client.noop()
        return {'status': 'tls_and_authentication_passed' if code == 250 else 'smtp_noop_failed', 'emails_sent': 0}
    except smtplib.SMTPAuthenticationError:
        return {'status': 'authentication_failed', 'emails_sent': 0}
    except ssl.SSLError:
        return {'status': 'tls_verification_failed', 'emails_sent': 0}
    except Exception:
        # Never print SMTP replies, exception text, host, username or password.
        return {'status': 'connection_failed', 'emails_sent': 0}
    finally:
        if client is not None:
            try:
                client.quit()
            except Exception:
                try:
                    client.close()
                except Exception:
                    pass

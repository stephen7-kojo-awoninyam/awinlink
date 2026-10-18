"""Shared web/mobile recovery policy. No account data in rate-limit keys or logs."""
import logging
from ipaddress import ip_address
import math
import time
from urllib.parse import urlsplit
from unicodedata import normalize

from django.conf import settings
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.core.validators import MaxLengthValidator
from django.core.cache import caches
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.crypto import salted_hmac

logger = logging.getLogger(__name__)
GENERIC_SENT = 'If an active account matches, password reset instructions have been sent.'
INVALID_LINK = 'This reset link is invalid or expired. Request a new reset email.'


class RecoveryUnavailable(Exception):
    pass


def client_address(request):
    # Forwarded headers are ignored unless the deployment explicitly trusts a
    # known number of sanitizing reverse proxies. Never accept the leftmost IP.
    header = settings.PASSWORD_RESET_TRUSTED_IP_HEADER
    if header and request.META.get(header):
        try:
            return str(ip_address(request.META[header].strip()))
        except ValueError:
            pass
    hops = settings.PASSWORD_RESET_TRUSTED_PROXY_COUNT
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')
    if hops > 0 and len(forwarded) >= hops:
        try:
            return str(ip_address(forwarded[-hops].strip()))
        except ValueError:
            pass
    return request.META.get('REMOTE_ADDR', '')


def consume(scope, identifier, limit, seconds):
    bucket = int(time.time()) // seconds
    digest = salted_hmac('password-recovery:' + scope, identifier).hexdigest()
    key = f'recovery:{scope}:{bucket}:{digest}'
    try:
        cache = caches[settings.PASSWORD_RESET_CACHE_ALIAS]
        if cache.add(key, 1, timeout=seconds + 1):
            return True
        try:
            return cache.incr(key) <= limit
        except ValueError:  # The bucket expired between add() and incr().
            return bool(cache.add(key, 1, timeout=seconds + 1))
    except Exception:
        logger.warning('Password recovery rate-limit service unavailable.')
        raise RecoveryUnavailable from None


def allow_request(request):
    return consume('request-ip', client_address(request), 5, 3600)


def allow_confirmation(request):
    return consume('confirm-ip', client_address(request), 20, 900)


class RecoveryForm(PasswordResetForm):
    def save(self, *, mobile=False, **kwargs):
        origin = urlsplit(settings.PASSWORD_RESET_BASE_URL)
        if (origin.scheme not in ('http', 'https') or not origin.netloc or origin.username
                or origin.password or origin.path or origin.query or origin.fragment
                or (not settings.DEBUG and origin.scheme != 'https')):
            raise ImproperlyConfigured('PASSWORD_RESET_BASE_URL must be a trusted HTTPS origin.')
        return super().save(
            domain_override=origin.netloc, use_https=origin.scheme == 'https',
            email_template_name='accounts/password_reset_email.txt',
            html_email_template_name='accounts/password_reset_email.html',
            subject_template_name='accounts/password_reset_subject.txt',
            extra_email_context={'mobile': mobile, 'expiry_minutes': math.ceil(settings.PASSWORD_RESET_TIMEOUT / 60)},
        )

    def send_mail(self, subject_template_name, email_template_name, context, from_email,
                  to_email, html_email_template_name=None):
        # Deliberately do not log SMTP exception text, email addresses or tokens.
        try:
            subject = ''.join(render_to_string(subject_template_name, context).splitlines())
            message = EmailMultiAlternatives(subject, render_to_string(email_template_name, context), from_email, [to_email])
            message.attach_alternative(render_to_string(html_email_template_name, context), 'text/html')
            message.send()
        except Exception:
            logger.warning('Password recovery email delivery failed.')


class RecoverySetPasswordForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.validators.append(MaxLengthValidator(4096))
            field.widget.attrs['maxlength'] = 4096


def send_recovery(form, *, mobile=False):
    email = normalize('NFKC', form.cleaned_data['email'].strip()).casefold()
    if consume('request-email', email, 3, 3600):
        form.save(mobile=mobile)

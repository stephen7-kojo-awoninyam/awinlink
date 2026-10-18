"""Select SMTP, Resend HTTPS or console without exposing environment values."""
from django.core.exceptions import ImproperlyConfigured

RESEND_BACKEND = 'accounts.email_backends.resend.EmailBackend'


def email_settings(environment, *, production):
    provider = environment.get('EMAIL_PROVIDER', 'smtp' if production else 'console').strip().lower()
    if provider not in ('smtp', 'resend', 'console'):
        raise ImproperlyConfigured('EMAIL_PROVIDER must be smtp, resend or console; value withheld.')
    if provider == 'resend':
        try:
            timeout = int(environment.get('RESEND_TIMEOUT', '10'))
            if not 1 <= timeout <= 60:
                raise ValueError
        except (TypeError, ValueError):
            raise ImproperlyConfigured('RESEND_TIMEOUT must be between 1 and 60 seconds; value withheld.') from None
        return {'EMAIL_PROVIDER': provider, 'EMAIL_BACKEND': RESEND_BACKEND,
                'RESEND_API_KEY': environment.get('RESEND_API_KEY', ''), 'RESEND_TIMEOUT': timeout,
                **sender_settings(environment)}
    return {'EMAIL_PROVIDER': provider,
            'EMAIL_BACKEND': 'django.core.mail.backends.smtp.EmailBackend' if provider == 'smtp'
                             else 'django.core.mail.backends.console.EmailBackend',
            **smtp_settings(environment)}


def sender_settings(environment):
    return {'DEFAULT_FROM_EMAIL': environment.get('DEFAULT_FROM_EMAIL', 'Awinlink <noreply@awinlink.com>'),
            'EMAIL_FROM_EXPLICIT': bool(environment.get('DEFAULT_FROM_EMAIL', '').strip()),
            'EMAIL_SENDER_DOMAIN': environment.get('EMAIL_SENDER_DOMAIN', '').strip().lower()}


def smtp_settings(environment):
    def flag(name, default):
        value = environment.get(name, str(default)).strip().lower()
        if value in ('true', '1', 'yes', 'on'):
            return True
        if value in ('false', '0', 'no', 'off'):
            return False
        raise ImproperlyConfigured(f'{name} must be a boolean; value withheld.')

    def number(name, default, minimum, maximum):
        try:
            value = int(environment.get(name, str(default)))
            if not minimum <= value <= maximum:
                raise ValueError
            return value
        except (TypeError, ValueError):
            raise ImproperlyConfigured(f'{name} is outside the allowed numeric range; value withheld.') from None

    implicit_tls = flag('EMAIL_USE_SSL', False)
    starttls = flag('EMAIL_USE_TLS', not implicit_tls)
    if implicit_tls and starttls:
        raise ImproperlyConfigured('EMAIL_USE_TLS and EMAIL_USE_SSL are mutually exclusive.')
    return {
        'EMAIL_HOST': environment.get('EMAIL_HOST', '').strip(),
        'EMAIL_PORT': number('EMAIL_PORT', 465 if implicit_tls else 587, 1, 65535),
        'EMAIL_TIMEOUT': number('EMAIL_TIMEOUT', 10, 1, 60),
        'EMAIL_USE_TLS': starttls,
        'EMAIL_USE_SSL': implicit_tls,
        'EMAIL_HOST_USER': environment.get('EMAIL_HOST_USER', ''),
        'EMAIL_HOST_PASSWORD': environment.get('EMAIL_HOST_PASSWORD', ''),
        **sender_settings(environment),
    }

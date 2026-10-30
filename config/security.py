"""Fail closed on unsafe production secrets, without including values in errors."""
from django.core.exceptions import ImproperlyConfigured


def environment_flag(environment, name, default=False):
    value = environment.get(name)
    if value is None:
        return default
    value = value.strip().lower()
    if value in {'true', '1', 'yes', 'on'}:
        return True
    if value in {'false', '0', 'no', 'off'}:
        return False
    raise ImproperlyConfigured(f'{name} must be a boolean; value withheld.')


def security_environment(environment):
    hosted = any(environment.get(name) for name in (
        'RAILWAY_ENVIRONMENT_NAME', 'RAILWAY_ENVIRONMENT', 'RAILWAY_ENVIRONMENT_ID',
        'RAILWAY_PROJECT_ID', 'RAILWAY_SERVICE_ID', 'RAILWAY_PUBLIC_DOMAIN',
        'RENDER', 'RENDER_EXTERNAL_HOSTNAME',
    ))
    mode = environment.get('AWINLINK_ENV', 'production').strip().lower()
    if mode not in {'development', 'production'}:
        raise ImproperlyConfigured('AWINLINK_ENV must be development or production; value withheld.')
    if hosted and mode != 'production':
        raise ImproperlyConfigured('Hosted services require production mode.')
    debug = environment_flag(environment, 'DEBUG', default=mode == 'development')
    if debug and mode == 'production':
        raise ImproperlyConfigured('DEBUG must be disabled in production.')
    return mode, hosted, debug


def validate_production_secret(secret, *, production):
    if production and (
        not isinstance(secret, str) or len(secret) < 50 or len(set(secret)) < 5
        or secret.startswith(('django-insecure-', 'local-development-'))
    ):
        raise ImproperlyConfigured('Production requires an explicit, strong SECRET_KEY (at least 50 characters).')

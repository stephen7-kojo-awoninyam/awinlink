"""Fail closed on unsafe production secrets, without including values in errors."""
from django.core.exceptions import ImproperlyConfigured


def validate_production_secret(secret, *, production):
    if production and (
        not isinstance(secret, str) or len(secret) < 50 or len(set(secret)) < 5
        or secret.startswith(('django-insecure-', 'local-development-'))
    ):
        raise ImproperlyConfigured('Production requires an explicit, strong SECRET_KEY (at least 50 characters).')

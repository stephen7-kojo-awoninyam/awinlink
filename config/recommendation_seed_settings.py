"""Isolated local sandbox; never uses DATABASE_URL or the application's DB."""
import os
from django.core.exceptions import ImproperlyConfigured
os.environ.setdefault('AWINLINK_ENV', 'development')
if os.environ['AWINLINK_ENV'].strip().lower() != 'development':
    raise ImproperlyConfigured('Recommendation sandbox settings are local-only.')
from .settings import *  # noqa: F403

DEBUG = True
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "recommendation-seed.sqlite3",  # noqa: F405
    }
}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
AWINLINK_RESOURCE_CACHE_ALIAS = 'default'

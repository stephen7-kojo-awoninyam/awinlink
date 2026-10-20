r"""Run security regressions locally; never use an application/production database.

Usage: .venv\Scripts\python.exe -B scripts/test_security_phase1.py [test labels]
Pass --all to run the full Django suite in the same isolated environment.
Add --fast for cheap fixture password hashes; production settings are unchanged.
"""
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
for name in ('RAILWAY_ENVIRONMENT_NAME', 'RAILWAY_ENVIRONMENT', 'RENDER'):
    os.environ.pop(name, None)
os.environ.update(DJANGO_SETTINGS_MODULE='config.settings', DATABASE_URL='', DEBUG='true',
                  SECRET_KEY='test-fixture-only-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ-abcdefgh')

from django.conf import settings
settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
settings.CHANNEL_LAYERS = {'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}
settings.CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
settings.AUTH_RATE_LIMIT_CACHE_ALIAS = settings.PASSWORD_RESET_CACHE_ALIAS = 'default'
settings.AUTH_RATE_LIMIT_REQUIRE_SHARED_CACHE = False
settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
settings.WEB_PUSH_PUBLIC_KEY = settings.WEB_PUSH_PRIVATE_KEY = settings.MOBILE_APNS_PRIVATE_KEY = ''
settings.STORAGES = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                     'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}
if '--fast' in sys.argv[1:]:
    settings.PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

import django
django.setup()
from django.core.cache import cache
from django.test.runner import DiscoverRunner


class IsolatedCacheResult(unittest.TextTestResult):
    def startTest(self, test):
        # Django does not clear cache between test cases. Limits must remain
        # effective within each test without carrying counters between fixtures.
        cache.clear()
        super().startTest(test)

    def addFailure(self, test, error):
        self.stream.writeln('\nFAILED TEST: ' + test.id())
        super().addFailure(test, error)

    def addError(self, test, error):
        self.stream.writeln('\nERROR IN TEST: ' + test.id())
        super().addError(test, error)


class SecurityRunner(DiscoverRunner):
    def get_resultclass(self):
        return IsolatedCacheResult


labels = [label for label in sys.argv[1:] if label not in ('--fast', '--failfast')] or [
    'accounts.test_security_hardening', 'accounts.test_token_logout', 'feed.test_post_authorization',
    'notifications.test_push_security', 'messaging.test_socket_revocation',
    'messaging.test_signaling_security', 'messaging.test_call_cancellation',
    'accounts.test_google_auth', 'accounts.test_mobile_flows', 'accounts.test_password_recovery',
    'organizations.test_permissions', 'organizations.test_workflow_permissions',
    'notifications.tests', 'config.test_media', 'feed.test_post_composer',
]
with tempfile.TemporaryDirectory(prefix='awinlink-phase1-tests-') as media:
    settings.MEDIA_ROOT = media
    result = SecurityRunner(verbosity=1, interactive=False, failfast='--failfast' in sys.argv).run_tests([] if labels == ['--all'] else labels)
raise SystemExit(bool(result))

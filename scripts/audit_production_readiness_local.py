"""Production readiness regressions against isolated local resources only."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.audit_turn_ice_local import offline_network


if __name__ == '__main__':
    requested_labels = [arg for arg in sys.argv[1:] if arg != '--trace-errors']
    trace_errors = '--trace-errors' in sys.argv[1:]
    # Windows crypto/runtime libraries need these OS paths; retain no app secrets.
    runtime = {key: os.environ[key] for key in ('SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATH', 'TEMP', 'TMP') if key in os.environ}
    with patch.dict(os.environ, {**runtime,
        'DJANGO_SETTINGS_MODULE': 'config.settings',
        'AWINLINK_ENV': 'development', 'DEBUG': 'true',
        'SECRET_KEY': 'local-audit-fixture-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ',
    }, clear=True), patch('dotenv.load_dotenv', return_value=False), offline_network():
        import django
        from django.conf import settings
        settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
        settings.CHANNEL_LAYERS = {'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}
        settings.CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
        settings.AUTH_RATE_LIMIT_CACHE_ALIAS = settings.PASSWORD_RESET_CACHE_ALIAS = 'default'
        settings.AUTH_RATE_LIMIT_REQUIRE_SHARED_CACHE = False
        settings.AWINLINK_RESOURCE_CACHE_ALIAS = 'default'
        settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
        settings.WEB_PUSH_PUBLIC_KEY = settings.WEB_PUSH_PRIVATE_KEY = settings.MOBILE_APNS_PRIVATE_KEY = ''
        settings.STORAGES = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}
        settings.PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
        settings.MIDDLEWARE = [item for item in settings.MIDDLEWARE if not item.startswith('whitenoise.')]
        django.setup()
        if trace_errors:
            import traceback
            from django.core.signals import got_request_exception

            def trace_fixture_exception(sender, **kwargs):
                traceback.print_exc()

            got_request_exception.connect(trace_fixture_exception, weak=False)
        from django.core.management import call_command
        from django.db.migrations.loader import MigrationLoader
        loader = MigrationLoader(None)
        print('Migration graph conflicts:', loader.detect_conflicts(), flush=True)
        labels = [
            'config.test_deployment',
            'config.test_production_security.ProductionDeploymentChecksTests',
            'config.test_resource_limits', 'config.test_http_limits',
            'config.test_upload_security', 'config.test_upload_quotas',
            'config.test_private_media_migration', 'config.test_media',
            'accounts.test_role_security', 'accounts.test_admin_login',
            'accounts.test_security_hardening', 'accounts.test_token_logout',
            'accounts.test_password_recovery', 'accounts.test_google_auth',
            'messaging.test_call_media', 'messaging.test_signaling_security',
            'messaging.test_socket_revocation', 'messaging.test_call_cancellation',
            'talents.test_verification_security', 'talents.test_profile_privacy',
            'portfolio.test_permissions', 'feed.test_post_authorization',
            'feed.test_linked_privacy', 'events.test_privacy',
            'notifications.test_push_security',
            'scripts.test_backup_readiness', 'scripts.test_railway_migration_audit',
        ]
        from django.core.cache import cache
        from django.test.runner import DiscoverRunner

        class IsolatedResult(unittest.TextTestResult):
            def startTest(self, test):
                cache.clear()
                super().startTest(test)

        class Runner(DiscoverRunner):
            def get_resultclass(self):
                return IsolatedResult

            def run_checks(self, databases):
                super().run_checks(databases)
                # makemigrations reads migration history and opens a connection.
                # Run it after test DB creation: SQLite deliberately ignores
                # close() on :memory:, so opening it earlier leaves the main
                # thread on :memory: while ASGI threads use the new test URI.
                call_command('makemigrations', check=True, dry_run=True, verbosity=1)

        # Do not open a database or reassign DATABASES before test DB creation.
        with tempfile.TemporaryDirectory(prefix='awinlink-readiness-') as media:
            settings.MEDIA_ROOT = media
            failures = Runner(verbosity=1, interactive=False).run_tests(requested_labels or labels)
        raise SystemExit(bool(failures))

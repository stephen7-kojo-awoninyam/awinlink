import os
from pathlib import Path
import subprocess
import sys

from django.core.checks import Tags, run_checks
from django.test import SimpleTestCase, override_settings

from .deployment_checks import shared_authentication_cache


class ProductionDeploymentChecksTests(SimpleTestCase):
    def test_synthetic_railway_configuration_passes_django_deployment_security_checks(self):
        from io import StringIO
        from unittest.mock import patch
        from django.core.management import call_command
        from .test_deployment import DeploymentSettingsTests
        configured = DeploymentSettingsTests().load_settings(RAILWAY_ENVIRONMENT_NAME='production',
            RAILWAY_PUBLIC_DOMAIN='fixture.up.railway.app', REDIS_URL='redis://127.0.0.1:9/0')
        names = ('DEBUG', 'SECRET_KEY', 'SECURE_SSL_REDIRECT', 'SESSION_COOKIE_SECURE', 'CSRF_COOKIE_SECURE',
            'SESSION_COOKIE_HTTPONLY', 'SECURE_HSTS_SECONDS', 'SECURE_HSTS_INCLUDE_SUBDOMAINS', 'SECURE_HSTS_PRELOAD',
            'ALLOWED_HOSTS', 'CSRF_TRUSTED_ORIGINS', 'CACHES', 'AUTH_RATE_LIMIT_CACHE_ALIAS', 'AUTH_RATE_LIMIT_REQUIRE_SHARED_CACHE',
            'AWINLINK_RESOURCE_CACHE_ALIAS', 'AWINLINK_ENV', 'HOSTED_PRODUCTION')
        with override_settings(**{name: configured[name] for name in names}), patch('redis.Redis.execute_command', side_effect=AssertionError('No live service check')):
            call_command('check', deploy=True, tags=['security'], fail_level='ERROR', stdout=StringIO(), stderr=StringIO())

    @override_settings(DEBUG=False, AUTH_RATE_LIMIT_REQUIRE_SHARED_CACHE=True,
        AUTH_RATE_LIMIT_CACHE_ALIAS='default', CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
    def test_deployment_checks_reject_local_auth_counters(self):
        self.assertIn('awinlink.E001', [error.id for error in run_checks(tags=[Tags.security], include_deployment_checks=True)])

    @override_settings(DEBUG=False, AUTH_RATE_LIMIT_REQUIRE_SHARED_CACHE=False)
    def test_deployment_checks_reject_disabling_the_production_requirement(self):
        self.assertEqual(shared_authentication_cache(None)[0].id, 'awinlink.E002')

    @override_settings(DEBUG=False, AUTH_RATE_LIMIT_REQUIRE_SHARED_CACHE=True, AUTH_RATE_LIMIT_CACHE_ALIAS='security',
        CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
                'security': {'BACKEND': 'django.core.cache.backends.redis.RedisCache', 'LOCATION': 'redis://127.0.0.1:9/0'}})
    def test_shared_redis_configuration_passes_without_contacting_a_service(self):
        from unittest.mock import patch
        with patch('redis.Redis.execute_command', side_effect=AssertionError('Checks must not contact Redis')):
            self.assertEqual(shared_authentication_cache(None), [])


class ProductionEntrypointTests(SimpleTestCase):
    root = Path(__file__).resolve().parents[1]
    secret = 'fixture-only-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ-abcdefgh'

    def run_entrypoint(self, entrypoint, **values):
        # Retain Windows runtime variables, never application secrets/services.
        environment = {key: os.environ[key] for key in ('SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATH', 'TEMP', 'TMP') if key in os.environ}
        environment.update(SECRET_KEY=self.secret, DATABASE_URL='sqlite:///:memory:', REDIS_URL='',
            DJANGO_SETTINGS_MODULE='config.settings', ALLOWED_HOSTS='testserver')
        environment.update(values)
        action = "importlib.import_module('" + entrypoint + "')" if entrypoint != 'command' else (
            "from django.core.management import call_command; call_command('check', tags=['security'])")
        code = "import importlib\nfrom unittest.mock import patch\nwith patch('dotenv.load_dotenv'):\n    " + action + "\n"
        return subprocess.run([sys.executable, '-B', '-c', code], cwd=self.root, env=environment,
            capture_output=True, text=True, timeout=60, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)

    def test_wsgi_asgi_and_commands_reject_implicit_development(self):
        for entrypoint in ('config.wsgi', 'config.asgi', 'command'):
            with self.subTest(entrypoint=entrypoint):
                result = self.run_entrypoint(entrypoint, DEBUG='true')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('DEBUG must be disabled in production', result.stderr)
                self.assertNotIn(self.secret, result.stderr)

    def test_wsgi_asgi_and_commands_boot_with_synthetic_railway_settings(self):
        for entrypoint in ('config.wsgi', 'config.asgi', 'command'):
            with self.subTest(entrypoint=entrypoint):
                result = self.run_entrypoint(entrypoint, RAILWAY_ENVIRONMENT_NAME='production',
                    RAILWAY_PUBLIC_DOMAIN='fixture.up.railway.app')
                self.assertEqual(result.returncode, 0, result.stderr[-1500:])

    def test_wsgi_asgi_and_commands_support_explicit_local_development(self):
        for entrypoint in ('config.wsgi', 'config.asgi', 'command'):
            with self.subTest(entrypoint=entrypoint):
                result = self.run_entrypoint(entrypoint, AWINLINK_ENV='development', DEBUG='true')
                self.assertEqual(result.returncode, 0, result.stderr[-1500:])

    def test_railway_cannot_boot_the_local_sandbox_settings(self):
        result = self.run_entrypoint('config.asgi', AWINLINK_ENV='production',
            RAILWAY_ENVIRONMENT_NAME='production', DJANGO_SETTINGS_MODULE='config.rising_talent_test_settings')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('sandbox settings are local-only', result.stderr)

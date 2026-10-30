import os
import runpy
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase
from django.core.exceptions import ImproperlyConfigured


class DeploymentSettingsTests(SimpleTestCase):
    def load_settings(self, **environment):
        environment.setdefault('SECRET_KEY', 'fixture-only-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ-abcdefgh')
        with patch.dict(os.environ, environment, clear=True), patch('dotenv.load_dotenv'):
            return runpy.run_path(str(Path(__file__).with_name('settings.py')))

    def test_railway_defaults_to_secure_production_settings(self):
        configured = self.load_settings(
            RAILWAY_ENVIRONMENT_NAME='production',
            RAILWAY_PUBLIC_DOMAIN='preview.up.railway.app',
            SECRET_KEY='fixture-only-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ-abcdefgh',
        )
        self.assertFalse(configured['DEBUG'])
        for key in ('SECURE_SSL_REDIRECT', 'SESSION_COOKIE_SECURE', 'CSRF_COOKIE_SECURE'):
            self.assertTrue(configured[key])
        self.assertIn('preview.up.railway.app', configured['ALLOWED_HOSTS'])
        self.assertIn('https://preview.up.railway.app', configured['CSRF_TRUSTED_ORIGINS'])
        self.assertEqual(configured['EMAIL_BACKEND'], 'django.core.mail.backends.smtp.EmailBackend')

    def test_render_origin_is_not_overwritten(self):
        configured = self.load_settings(RENDER='true', RENDER_EXTERNAL_HOSTNAME='example.onrender.com')
        self.assertIn('https://example.onrender.com', configured['CSRF_TRUSTED_ORIGINS'])

    def test_explicit_production_and_custom_domains(self):
        configured = self.load_settings(
            DEBUG='False', ALLOWED_HOSTS='awinlink.com,www.awinlink.com',
            CSRF_TRUSTED_ORIGINS='https://awinlink.com,https://www.awinlink.com',
        )
        self.assertTrue(configured['SECURE_SSL_REDIRECT'])
        self.assertIn('awinlink.com', configured['ALLOWED_HOSTS'])
        self.assertIn('https://www.awinlink.com', configured['CSRF_TRUSTED_ORIGINS'])

    def test_explicit_local_development_remains_usable(self):
        configured = self.load_settings(AWINLINK_ENV='development')
        self.assertTrue(configured['DEBUG'])
        self.assertNotIn('SECURE_SSL_REDIRECT', configured)
        self.assertEqual(configured['EMAIL_BACKEND'], 'django.core.mail.backends.console.EmailBackend')

    def test_turn_environment_flags_are_loaded_without_client_secrets(self):
        configured = self.load_settings(
            AWINLINK_ENV='development',
            TURN_REQUIRED='true', CALL_ICE_TRANSPORT_POLICY='relay',
            TURN_CREDENTIAL_TTL_SECONDS='1800',
        )
        self.assertTrue(configured['TURN_REQUIRED'])
        self.assertEqual(configured['CALL_ICE_TRANSPORT_POLICY'], 'relay')
        self.assertEqual(configured['TURN_CREDENTIAL_TTL_SECONDS'], '1800')

    def test_recovery_defaults_use_canonical_origin_and_shared_redis(self):
        configured = self.load_settings(RAILWAY_ENVIRONMENT_NAME='production',
            RAILWAY_PUBLIC_DOMAIN='app.example.com', REDIS_URL='redis://127.0.0.1:6379/0')
        self.assertEqual(configured['PASSWORD_RESET_BASE_URL'], 'https://app.example.com')
        self.assertEqual(configured['PASSWORD_RESET_TIMEOUT'], 3600)
        self.assertEqual(configured['PASSWORD_RESET_CACHE_ALIAS'], 'password_reset')
        self.assertEqual(configured['PASSWORD_RESET_TRUSTED_IP_HEADER'], 'HTTP_X_REAL_IP')

    def test_smtp_ssl_uses_465_and_disables_starttls_by_default(self):
        configured = self.load_settings(AWINLINK_ENV='development', EMAIL_USE_SSL='true')
        self.assertEqual(configured['EMAIL_PORT'], 465)
        self.assertTrue(configured['EMAIL_USE_SSL'])
        self.assertFalse(configured['EMAIL_USE_TLS'])
        self.assertEqual(configured['EMAIL_TIMEOUT'], 10)

    def test_railway_can_explicitly_select_resend_https_without_smtp(self):
        configured = self.load_settings(RAILWAY_ENVIRONMENT_NAME='production', EMAIL_PROVIDER='resend', RESEND_API_KEY='re_synthetic_key')
        self.assertEqual(configured['EMAIL_BACKEND'], 'accounts.email_backends.resend.EmailBackend')
        self.assertEqual(configured['RESEND_TIMEOUT'], 10)
        self.assertNotIn('EMAIL_HOST_PASSWORD', configured)

    def test_custom_host_and_missing_mode_default_to_production(self):
        configured = self.load_settings(ALLOWED_HOSTS='app.example.invalid')
        self.assertEqual(configured['AWINLINK_ENV'], 'production')
        self.assertFalse(configured['DEBUG'])
        for key in ('SECURE_SSL_REDIRECT', 'SESSION_COOKIE_SECURE', 'CSRF_COOKIE_SECURE',
                    'AUTH_RATE_LIMIT_REQUIRE_SHARED_CACHE', 'SESSION_COOKIE_HTTPONLY'):
            self.assertTrue(configured[key])
        self.assertIsNone(configured['SECURE_PROXY_SSL_HEADER'])
        self.assertFalse(configured['SECURE_HSTS_PRELOAD'])
        self.assertFalse(configured['SECURE_HSTS_INCLUDE_SUBDOMAINS'])

    def test_production_default_requires_a_strong_explicit_secret(self):
        for secret in ('', 'short', 'local-development-secret-change-this'):
            with self.subTest(secret_type='fixture'), self.assertRaises(ImproperlyConfigured):
                self.load_settings(SECRET_KEY=secret)

    def test_debug_true_without_development_opt_in_is_rejected(self):
        with self.assertRaises(ImproperlyConfigured): self.load_settings(DEBUG='true')

    def test_hosted_services_cannot_opt_into_development(self):
        for marker in ('RAILWAY_ENVIRONMENT_NAME', 'RAILWAY_PROJECT_ID', 'RAILWAY_PUBLIC_DOMAIN', 'RENDER', 'RENDER_EXTERNAL_HOSTNAME'):
            with self.subTest(marker=marker), self.assertRaises(ImproperlyConfigured):
                self.load_settings(**{marker: 'fixture', 'AWINLINK_ENV': 'development'})

    def test_invalid_modes_and_boolean_values_are_rejected_without_echo(self):
        for name in ('AWINLINK_ENV', 'DEBUG', 'AWINLINK_TRUST_PROXY_HEADERS', 'SECURE_HSTS_PRELOAD'):
            with self.subTest(name=name), self.assertRaises(ImproperlyConfigured) as error:
                self.load_settings(**{name: 'invalid-sensitive-fixture'})
            self.assertNotIn('invalid-sensitive-fixture', str(error.exception))

    def test_railway_preserves_proxy_tls_cookies_domains_and_hsts(self):
        configured = self.load_settings(RAILWAY_ENVIRONMENT_NAME='production', RAILWAY_PUBLIC_DOMAIN='app.up.railway.app')
        self.assertEqual(configured['SECURE_PROXY_SSL_HEADER'], ('HTTP_X_FORWARDED_PROTO', 'https'))
        self.assertTrue(configured['SECURE_HSTS_PRELOAD']); self.assertTrue(configured['SECURE_HSTS_INCLUDE_SUBDOMAINS'])
        self.assertEqual(configured['SECURE_HSTS_SECONDS'], 31536000)
        self.assertIn('app.up.railway.app', configured['ALLOWED_HOSTS'])
        self.assertEqual(configured['SESSION_COOKIE_SAMESITE'], 'Lax')
        self.assertEqual(configured['CSRF_COOKIE_SAMESITE'], 'Lax')

    def test_custom_sanitizing_proxy_can_be_trusted_explicitly(self):
        configured = self.load_settings(AWINLINK_TRUST_PROXY_HEADERS='true')
        self.assertEqual(configured['SECURE_PROXY_SSL_HEADER'], ('HTTP_X_FORWARDED_PROTO', 'https'))

    def test_wildcard_hosts_and_http_csrf_origins_are_not_allowed_in_production(self):
        for values in ({'ALLOWED_HOSTS': '*'}, {'CSRF_TRUSTED_ORIGINS': 'http://app.example.invalid'}):
            with self.subTest(values=values), self.assertRaises(ImproperlyConfigured): self.load_settings(**values)

    def test_untrusted_forwarded_tls_header_cannot_bypass_https_redirect(self):
        from django.test import override_settings
        configured = self.load_settings()
        with override_settings(SECURE_SSL_REDIRECT=configured['SECURE_SSL_REDIRECT'], SECURE_PROXY_SSL_HEADER=configured['SECURE_PROXY_SSL_HEADER']):
            response = self.client.get('/admin/login/', HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], 'https://testserver/admin/login/')

    def test_railway_proxy_https_does_not_create_a_redirect_loop(self):
        from django.test import override_settings
        configured = self.load_settings(RAILWAY_ENVIRONMENT_NAME='production')
        with override_settings(SECURE_SSL_REDIRECT=True, SECURE_PROXY_SSL_HEADER=configured['SECURE_PROXY_SSL_HEADER'], CSRF_COOKIE_SECURE=True):
            response = self.client.get('/admin/login/', HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.cookies['csrftoken']['secure'])

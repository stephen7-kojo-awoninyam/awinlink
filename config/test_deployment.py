import os
import runpy
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase


class DeploymentSettingsTests(SimpleTestCase):
    def load_settings(self, **environment):
        with patch.dict(os.environ, environment, clear=True), patch('dotenv.load_dotenv'):
            return runpy.run_path(str(Path(__file__).with_name('settings.py')))

    def test_railway_defaults_to_secure_production_settings(self):
        configured = self.load_settings(
            RAILWAY_ENVIRONMENT_NAME='production',
            RAILWAY_PUBLIC_DOMAIN='preview.up.railway.app',
            SECRET_KEY='test-only-production-key',
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

    def test_local_development_defaults_remain_usable(self):
        configured = self.load_settings()
        self.assertTrue(configured['DEBUG'])
        self.assertNotIn('SECURE_SSL_REDIRECT', configured)
        self.assertEqual(configured['EMAIL_BACKEND'], 'django.core.mail.backends.console.EmailBackend')

    def test_turn_environment_flags_are_loaded_without_client_secrets(self):
        configured = self.load_settings(
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
        configured = self.load_settings(EMAIL_USE_SSL='true')
        self.assertEqual(configured['EMAIL_PORT'], 465)
        self.assertTrue(configured['EMAIL_USE_SSL'])
        self.assertFalse(configured['EMAIL_USE_TLS'])
        self.assertEqual(configured['EMAIL_TIMEOUT'], 10)

    def test_railway_can_explicitly_select_resend_https_without_smtp(self):
        configured = self.load_settings(RAILWAY_ENVIRONMENT_NAME='production', EMAIL_PROVIDER='resend', RESEND_API_KEY='re_synthetic_key')
        self.assertEqual(configured['EMAIL_BACKEND'], 'accounts.email_backends.resend.EmailBackend')
        self.assertEqual(configured['RESEND_TIMEOUT'], 10)
        self.assertNotIn('EMAIL_HOST_PASSWORD', configured)

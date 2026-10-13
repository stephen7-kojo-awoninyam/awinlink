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

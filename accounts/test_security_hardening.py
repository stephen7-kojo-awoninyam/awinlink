import os
import runpy
from pathlib import Path
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, SimpleTestCase, override_settings, Client, RequestFactory
from rest_framework.test import APIClient
from config.security import validate_production_secret


@override_settings(AUTH_RATE_LIMIT_CACHE_ALIAS='default', AUTH_RATE_LIMIT_REQUIRE_SHARED_CACHE=False,
    AUTH_RATE_LIMITS={'login': {'ip': (20, 900), 'identity': (2, 900)},
                     'registration': {'ip': (2, 900)}, 'google': {'identity': (2, 900)}})
class AuthenticationHardeningTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username='limited-login', password='ValidAuditPassword123!')
        self.api = APIClient()

    def tearDown(self):
        cache.clear()

    def test_web_and_api_share_normalized_login_limit(self):
        self.assertEqual(self.api.post('/api/auth/login/', {'username': self.user.username, 'password': 'wrong'}).status_code, 401)
        self.assertEqual(self.client.post('/accounts/login/', {'username': self.user.username.upper(), 'password': 'wrong'}).status_code, 200)
        response = self.api.post('/api/auth/login/', {'username': self.user.username, 'password': 'ValidAuditPassword123!'})
        self.assertEqual(response.status_code, 429)
        self.assertIn('Retry-After', response)

    def test_legitimate_login_still_issues_tokens(self):
        response = self.api.post('/api/auth/login/', {'username': self.user.username, 'password': 'ValidAuditPassword123!'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_cache_failure_fails_closed_without_leaking_details(self):
        broken = Mock()
        broken.add.side_effect = RuntimeError('redis://sensitive-credential@private-host')
        with patch('accounts.security.caches', {'default': broken}):
            response = self.api.post('/api/auth/login/', {'username': self.user.username, 'password': 'ValidAuditPassword123!'})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('sensitive-credential', str(response.data))

    @override_settings(AUTH_RATE_LIMIT_REQUIRE_SHARED_CACHE=True)
    def test_production_refuses_process_local_auth_counters(self):
        self.assertEqual(self.api.post('/api/auth/login/', {'username': self.user.username, 'password': 'wrong'}).status_code, 503)

    def test_authenticated_google_link_attempts_are_limited(self):
        self.api.force_authenticate(self.user)
        for _ in range(2):
            self.assertEqual(self.api.post('/api/auth/google/start/', {'link': True, 'password': 'wrong'}, format='json').status_code, 400)
        self.assertEqual(self.api.post('/api/auth/google/start/', {'link': True, 'password': 'wrong'}, format='json').status_code, 429)

    def test_web_csrf_protection_is_preserved(self):
        self.assertEqual(Client(enforce_csrf_checks=True).post('/accounts/login/', {'username': self.user.username, 'password': 'wrong'}).status_code, 403)

    @override_settings(AUTH_RATE_LIMITS={'push': {'identity': (2, 900)}})
    def test_authenticated_push_limit_cannot_be_changed_by_submitted_username(self):
        from accounts.views import authentication_limit_response
        for index in range(3):
            request = RequestFactory().post('/notifications/push/', {'username': f'fake-{index}'})
            request.user = self.user
            response = authentication_limit_response(request, 'push')
            if index < 2:
                self.assertIsNone(response)
            else:
                self.assertEqual(response.status_code, 429)

    def test_malformed_and_oversized_credentials_are_rejected_before_authentication(self):
        with patch('api.views.authenticate') as authenticate:
            self.assertEqual(self.api.post('/api/auth/login/', [], format='json').status_code, 400)
            self.assertEqual(self.api.post('/api/auth/login/', {'username': self.user.username, 'password': 'x' * 4097}, format='json').status_code, 400)
            authenticate.assert_not_called()

    @override_settings(AUTH_RATE_LIMITS={'login': {'ip': (2, 900)}})
    def test_malformed_json_still_consumes_the_ip_budget(self):
        for _ in range(2):
            self.assertEqual(self.api.generic('POST', '/api/auth/login/', data='{', content_type='application/json').status_code, 400)
        self.assertEqual(self.api.generic('POST', '/api/auth/login/', data='{', content_type='application/json').status_code, 429)


class ProductionSecretTests(SimpleTestCase):
    strong = 'audit-fixture-only-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ-abcdefgh'

    def test_missing_weak_and_known_development_values_are_rejected(self):
        for value in [None, '', 'short', 'a' * 60, 'django-insecure-' + 'abcd' * 20, 'local-development-secret-change-this']:
            with self.subTest(value_type=type(value).__name__), self.assertRaises(ImproperlyConfigured):
                validate_production_secret(value, production=True)
        validate_production_secret(self.strong, production=True)
        validate_production_secret('local-development-secret-change-this', production=False)

    def test_hosted_startup_rejects_debug_and_missing_secret(self):
        settings_file = Path(__file__).resolve().parents[1] / 'config/settings.py'
        for values in [{'RAILWAY_ENVIRONMENT_NAME': 'production'},
                       {'RAILWAY_ENVIRONMENT_NAME': 'production', 'DEBUG': 'true', 'SECRET_KEY': self.strong}]:
            with patch.dict(os.environ, values, clear=True), patch('dotenv.load_dotenv'), self.assertRaises(ImproperlyConfigured):
                runpy.run_path(str(settings_file))

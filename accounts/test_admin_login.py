import os
import json
import subprocess
import sys
from pathlib import Path
from unittest import skipUnless
from unittest.mock import Mock, patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.core.cache.backends.filebased import FileBasedCache
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from .admin_site import SecureAdminSite
from .models import UserBlock


@override_settings(AUTH_RATE_LIMIT_CACHE_ALIAS='default', AUTH_RATE_LIMIT_REQUIRE_SHARED_CACHE=False,
    AUTH_RATE_LIMITS={'login': {'ip': (20, 900), 'identity': (2, 900)}},
    PASSWORD_RESET_TRUSTED_PROXY_COUNT=0, PASSWORD_RESET_TRUSTED_IP_HEADER='')
class AdminLoginSecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.password = 'FixtureAdminPassword123!'
        self.superuser = get_user_model().objects.create_superuser('site-admin', 'fixture@example.invalid', self.password)
        self.browser = Client(enforce_csrf_checks=True)

    def tearDown(self):
        cache.clear()

    def post(self, username=None, password=None, **headers):
        self.browser.get(reverse('admin:login'))
        return self.browser.post(reverse('admin:login'), {
            'username': username or self.superuser.username, 'password': password or 'wrong',
            'csrfmiddlewaretoken': self.browser.cookies['csrftoken'].value,
        }, **headers)

    def test_default_registry_urls_and_legitimate_superuser_login_are_preserved(self):
        self.assertIsInstance(admin.site, SecureAdminSite)
        self.assertIn(UserBlock, admin.site._registry)
        self.assertEqual(reverse('admin:accounts_userblock_changelist'), '/admin/accounts/userblock/')
        response = self.post(password=self.password)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.browser.session['_auth_user_id']), self.superuser.pk)
        self.assertEqual(self.browser.get(reverse('admin:index')).status_code, 200)
        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.is_active); self.assertTrue(self.superuser.is_staff); self.assertTrue(self.superuser.is_superuser)
        self.assertTrue(self.superuser.check_password(self.password))

    def test_staff_with_existing_permissions_retains_access(self):
        staff = get_user_model().objects.create_user('staff-login', password=self.password, is_staff=True)
        staff.user_permissions.add(Permission.objects.get(codename='view_userblock', content_type__app_label='accounts'))
        self.assertEqual(self.post(username=staff.username, password=self.password).status_code, 302)
        self.assertEqual(self.browser.get(reverse('admin:accounts_userblock_changelist')).status_code, 200)

    def test_application_admin_role_without_staff_flag_does_not_gain_django_admin(self):
        actor = get_user_model().objects.create_user('app-admin-only', password=self.password, role='ADMIN')
        self.assertEqual(self.post(username=actor.username, password=self.password).status_code, 200)
        self.assertNotIn('_auth_user_id', self.browser.session)

    def test_repeated_attempts_return_429_before_password_authentication(self):
        for _ in range(2): self.assertEqual(self.post().status_code, 200)
        with patch('django.contrib.auth.forms.authenticate') as authenticate:
            response = self.post(password=self.password)
        self.assertEqual(response.status_code, 429); self.assertIn('Retry-After', response)
        self.assertIn('no-store', response['Cache-Control']); authenticate.assert_not_called()
        self.assertNotIn(self.password, response.content.decode())
        self.assertNotIn('_auth_user_id', self.browser.session)

    def test_all_login_surfaces_share_the_normalized_identity_budget(self):
        api = APIClient()
        self.assertEqual(api.post('/api/auth/login/', {'username': 'SITE-ADMIN', 'password': 'wrong'}).status_code, 401)
        self.assertEqual(self.client.post('/accounts/login/', {'username': 'ｓｉｔｅ－ａｄｍｉｎ', 'password': 'wrong'}).status_code, 200)
        self.assertEqual(self.post(password=self.password).status_code, 429)
        cache.clear()
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(api.post('/api/auth/login/', {'username': 'site-admin', 'password': 'wrong'}).status_code, 401)
        self.assertEqual(self.client.post('/accounts/login/', {'username': 'site-admin', 'password': self.password}).status_code, 429)

    def test_account_deletion_signin_cannot_bypass_admin_budget(self):
        for _ in range(2): self.assertEqual(self.post().status_code, 200)
        page = self.browser.get('/delete-account/sign-in/')
        self.assertEqual(page.status_code, 200)
        with patch('django.contrib.auth.forms.authenticate') as authenticate:
            response = self.browser.post('/delete-account/sign-in/', {'username': 'site-admin', 'password': self.password,
                'csrfmiddlewaretoken': self.browser.cookies['csrftoken'].value})
        self.assertEqual(response.status_code, 429); authenticate.assert_not_called()
        self.assertNotIn('_auth_user_id', self.browser.session)

    def test_account_deletion_signin_keeps_normal_login_redirect_and_csrf(self):
        actor = get_user_model().objects.create_user('deletion-login', password=self.password)
        response = self.browser.post('/delete-account/sign-in/', {'username': actor.username, 'password': self.password})
        self.assertEqual(response.status_code, 403)
        self.browser.get('/delete-account/sign-in/')
        response = self.browser.post('/delete-account/sign-in/', {'username': actor.username, 'password': self.password,
            'csrfmiddlewaretoken': self.browser.cookies['csrftoken'].value})
        self.assertEqual(response.status_code, 302); self.assertEqual(response['Location'], '/delete-account/')
        self.assertEqual(int(self.browser.session['_auth_user_id']), actor.pk)

    @override_settings(AUTH_RATE_LIMITS={'login': {'ip': (1, 900)}})
    def test_untrusted_forwarded_headers_do_not_reset_ip_budget(self):
        self.assertEqual(self.post(username='missing-one', HTTP_X_FORWARDED_FOR='192.0.2.1', HTTP_X_REAL_IP='192.0.2.2').status_code, 200)
        self.assertEqual(self.post(username='missing-two', HTTP_X_FORWARDED_FOR='198.51.100.1', HTTP_X_REAL_IP='198.51.100.2').status_code, 429)

    @override_settings(PASSWORD_RESET_TRUSTED_IP_HEADER='HTTP_X_REAL_IP', AUTH_RATE_LIMITS={'login': {'ip': (1, 900)}})
    def test_configured_sanitizing_proxy_identity_is_used(self):
        self.assertEqual(self.post(username='one', HTTP_X_REAL_IP='192.0.2.1').status_code, 200)
        self.assertEqual(self.post(username='two', HTTP_X_REAL_IP='192.0.2.2').status_code, 200)
        self.assertEqual(self.post(username='three', HTTP_X_REAL_IP='192.0.2.1').status_code, 429)

    def test_csrf_is_checked_before_consuming_attempt_budget(self):
        with patch('accounts.security.enforce_auth_limit') as limiter:
            response = self.browser.post(reverse('admin:login'), {'username': 'site-admin', 'password': 'wrong'})
        self.assertEqual(response.status_code, 403); limiter.assert_not_called()
        self.assertEqual(self.post().status_code, 200)

    @override_settings(AUTH_RATE_LIMITS={'login': {'ip': (1, 900), 'identity': (1, 900)}})
    def test_login_form_get_and_head_do_not_consume_budget(self):
        for _ in range(3):
            self.assertEqual(self.browser.get(reverse('admin:login')).status_code, 200)
            self.assertEqual(self.browser.head(reverse('admin:login')).status_code, 200)
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(self.post().status_code, 429)

    def test_cache_outage_fails_closed_and_redacts_provider_details(self):
        broken = Mock(); broken.add.side_effect = RuntimeError('redis://private-secret@fixture.invalid')
        with patch('accounts.security.caches', {'default': broken}), patch('django.contrib.auth.forms.authenticate') as authenticate:
            response = self.post(password=self.password)
        self.assertEqual(response.status_code, 503); authenticate.assert_not_called()
        self.assertIn('no-store', response['Cache-Control']); self.assertNotIn('private-secret', response.content.decode())

    @override_settings(AUTH_RATE_LIMIT_REQUIRE_SHARED_CACHE=True)
    def test_production_refuses_process_local_or_nonatomic_cache(self):
        self.assertEqual(self.post(password=self.password).status_code, 503)
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            with patch('accounts.security.caches', {'default': FileBasedCache(directory, {})}):
                self.assertEqual(self.post(password=self.password).status_code, 503)

    def test_missing_or_invalid_limit_policy_is_a_controlled_unavailable_response(self):
        for policy in ({}, {'login': {}}, {'login': {'ip': (0, 900)}}, {'login': {'ip': (2, -1)}}):
            with self.subTest(policy=policy), override_settings(AUTH_RATE_LIMITS=policy):
                self.assertEqual(self.post(password=self.password).status_code, 503)

    @override_settings(AUTH_RATE_LIMITS={'login': {'identity': (1, 10)}})
    def test_temporary_budget_expires_without_locking_or_modifying_account(self):
        with patch('accounts.security.time.time', return_value=1000):
            self.assertEqual(self.post().status_code, 200)
            self.assertEqual(self.post().status_code, 429)
        with patch('accounts.security.time.time', return_value=1021):
            self.assertEqual(self.post(password=self.password).status_code, 302)
        self.superuser.refresh_from_db(); self.assertTrue(self.superuser.is_active)

    def test_cache_keys_do_not_contain_raw_login_identity_or_password(self):
        self.post()
        keys = ' '.join(str(key) for key in cache._cache)
        self.assertNotIn('site-admin', keys); self.assertNotIn(self.password, keys); self.assertNotIn('127.0.0.1', keys)


@skipUnless(os.environ.get('AWINLINK_SECURITY_TEST_REDIS_URL'), 'Requires the isolated Redis test runner.')
class SharedAdminRedisTests(SimpleTestCase):
    def test_admin_attempt_budget_is_atomic_across_independent_workers(self):
        root = Path(__file__).resolve().parents[1]
        environment = os.environ.copy()
        processes = [subprocess.Popen([sys.executable, '-B', str(root / 'scripts/admin_login_worker.py'), str(index)],
            cwd=root, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0) for index in range(2)]
        reports = []
        try:
            for process in processes:
                output, errors = process.communicate(timeout=60)
                self.assertEqual(process.returncode, 0, errors[-1500:])
                reports.append(json.loads(output))
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate(); process.wait(timeout=5)
        statuses = [status for report in reports for status in report['statuses']]
        self.assertEqual(statuses.count(200), 3, reports)
        self.assertEqual(statuses.count(429), 7, reports)
        self.assertEqual(sum(report['password_checks'] for report in reports), 3)

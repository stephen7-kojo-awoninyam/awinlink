"""HTTPS browser form submissions, with Django's real CSRF middleware enabled."""
from html.parser import HTMLParser
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from accounts.models import User


class AuthPageParser(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.policy = None
        self.tokens = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta' and attrs.get('name') == 'referrer':
            self.policy = attrs.get('content')
        if tag == 'input' and attrs.get('name') == 'csrfmiddlewaretoken':
            self.tokens.append(attrs['value'])


@override_settings(
    DEBUG=False,
    ALLOWED_HOSTS=['awinlink-production.up.railway.app'],
    CSRF_TRUSTED_ORIGINS=['https://awinlink-production.up.railway.app'],
    SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'),
    SECURE_SSL_REDIRECT=True,
    SESSION_COOKIE_SECURE=True,
    CSRF_COOKIE_SECURE=True,
    SECURE_REFERRER_POLICY='same-origin',
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.InMemoryStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    },
)
class LoginCsrfTests(TestCase):
    origin = 'https://awinlink-production.up.railway.app'
    paths = ('/accounts/login/', '/accounts/google/start/')

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='csrf-member', password='Fixture-only-pass123!')

    def setUp(self):
        cache.clear()
        self.browser = Client(enforce_csrf_checks=True,
            HTTP_HOST='awinlink-production.up.railway.app', HTTP_X_FORWARDED_PROTO='https')
        self.page = self.browser.get('/accounts/login/')
        self.parsed = AuthPageParser(self.page.content.decode())
        self.data = {'username': self.user.username, 'password': 'Fixture-only-pass123!',
                     'csrfmiddlewaretoken': self.parsed.tokens[-1]}

    def test_login_document_preserves_same_origin_form_metadata(self):
        self.assertEqual(self.page.status_code, 200)
        self.assertTrue(self.page.wsgi_request.is_secure())
        self.assertTrue(self.page.cookies['csrftoken']['secure'])
        self.assertEqual(len(self.parsed.tokens), 2)
        self.assertEqual(self.page['Referrer-Policy'], 'same-origin')
        self.assertEqual(self.parsed.policy, 'same-origin')
        self.assertEqual(self.page['X-Frame-Options'], 'DENY')
        self.assertNotIn('sandbox', self.page.get('Content-Security-Policy', ''))

    def test_null_origin_reproduces_production_failure_even_with_valid_token(self):
        for path in self.paths:
            with self.subTest(path=path), self.assertLogs('django.security.csrf', level='WARNING') as logs:
                response = self.browser.post(path, self.data, HTTP_ORIGIN='null')
                self.assertEqual(response.status_code, 403)
                self.assertIn('Origin checking failed - null', logs.output[0])

    def test_same_origin_password_login_creates_session(self):
        response = self.browser.post(self.paths[0], self.data, HTTP_ORIGIN=self.origin)
        self.assertRedirects(response, '/dashboard/', fetch_redirect_response=False)
        self.assertEqual(self.browser.session['_auth_user_id'], str(self.user.pk))

    def test_same_origin_google_start_reaches_oauth_and_binds_session(self):
        # No provider calls or credentials: isolate only OAuth initialization.
        from types import SimpleNamespace
        with patch('accounts.google_views.begin', return_value=(
            SimpleNamespace(state='fixture-state'), 'https://accounts.google.com/o/oauth2/v2/auth', None)) as begin:
            response = self.browser.post(self.paths[1], self.data, HTTP_ORIGIN=self.origin)
        self.assertEqual(response.status_code, 302)
        begin.assert_called_once()
        self.assertEqual(self.browser.session['google_state'], 'fixture-state')
        self.assertEqual(response['Referrer-Policy'], 'no-referrer')

    def test_https_referer_fallback_allows_password_login(self):
        response = self.browser.post(self.paths[0], self.data,
                                     HTTP_REFERER=self.origin + '/accounts/login/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('_auth_user_id', self.browser.session)

    def test_invalid_origins_and_missing_metadata_remain_rejected(self):
        for path in self.paths:
            for headers in ({'HTTP_ORIGIN': 'https://attacker.example'},
                            {'HTTP_ORIGIN': 'null', 'HTTP_REFERER': self.origin + '/'},
                            {'HTTP_REFERER': 'https://attacker.example/'}, {}):
                with self.subTest(path=path, headers=headers):
                    self.assertEqual(self.browser.post(path, self.data, **headers).status_code, 403)

    def test_same_origin_requires_valid_cookie_and_token(self):
        for path in self.paths:
            for token in ('', 'x' * 64):
                with self.subTest(path=path, token=token):
                    data = {**self.data, 'csrfmiddlewaretoken': token}
                    self.assertEqual(self.browser.post(path, data, HTTP_ORIGIN=self.origin).status_code, 403)
            cookieless = Client(enforce_csrf_checks=True,
                HTTP_HOST='awinlink-production.up.railway.app', HTTP_X_FORWARDED_PROTO='https')
            self.assertEqual(cookieless.post(path, self.data, HTTP_ORIGIN=self.origin).status_code, 403)

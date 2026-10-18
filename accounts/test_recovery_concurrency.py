from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.db import close_old_connections, connection
from django.test import Client, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

from . import test_password_recovery as fixtures


@skipUnless(connection.vendor == 'postgresql', 'PostgreSQL row locks required')
@override_settings(**fixtures.PasswordRecoveryTests._overridden_settings)
class PasswordRecoveryConcurrencyTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username='reset-race', email='reset@example.com', password='Original!9-Password')
        self.uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        self.token = default_token_generator.make_token(self.user)

    def race(self, *operations):
        barrier = Barrier(len(operations))
        def run(operation):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout='8s'")
                barrier.wait(timeout=10)
                return operation()
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=len(operations)) as pool:
            futures = [pool.submit(run, operation) for operation in operations]
            return [future.result(timeout=25) for future in futures]

    def submit(self, password):
        return APIClient().post('/api/auth/password-reset/confirm/', {
            'uid': self.uid, 'token': self.token, 'new_password1': password,
            'new_password2': password}, format='json').status_code

    def test_two_api_confirmations_only_one_succeeds(self):
        outcomes = self.race(lambda: self.submit('First!9-NewPassword'), lambda: self.submit('Second!9-NewPassword'))
        self.assertEqual(sorted(outcomes), [200, 400])
        self.user.refresh_from_db()
        self.assertFalse(default_token_generator.check_token(self.user, self.token))

    def test_web_and_api_cannot_both_consume_one_token(self):
        browser = Client()
        landing = browser.get(reverse('password_reset_confirm', kwargs={'uidb64': self.uid, 'token': self.token}))
        self.assertEqual(landing.status_code, 302)
        def web():
            result = browser.post(landing.url, {'new_password1': 'Web!9-NewPassword', 'new_password2': 'Web!9-NewPassword'})
            return result.status_code == 302
        outcomes = self.race(web, lambda: self.submit('Api!9-NewPassword') == 200)
        self.assertEqual(sum(outcomes), 1)
        self.user.refresh_from_db()
        self.assertFalse(default_token_generator.check_token(self.user, self.token))

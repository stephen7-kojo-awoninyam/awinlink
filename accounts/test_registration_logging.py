from contextlib import redirect_stdout
from io import StringIO

from django.test import TestCase
from django.urls import reverse


class RegistrationLoggingTests(TestCase):
    def test_registration_does_not_print_passwords_or_submitted_personal_data(self):
        output = StringIO()
        with redirect_stdout(output):
            response = self.client.post(reverse('register'), {
                'username': 'audit_log_user', 'email': 'audit-log@example.com',
                'password1': 'SyntheticPrivateValue123!', 'password2': 'SyntheticPrivateValue123!',
            })
        self.assertEqual(response.status_code, 200)
        for private_value in ('SyntheticPrivateValue123!', 'audit-log@example.com', 'audit_log_user'):
            self.assertNotIn(private_value, output.getvalue())

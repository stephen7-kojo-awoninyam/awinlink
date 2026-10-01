from django.test import TestCase

from accounts.forms import UserRegistrationForm


class UserRegistrationRoleTests(TestCase):
    def test_registration_requires_account_type_selection(self):
        form = UserRegistrationForm(
            data={
                "first_name": "Ada",
                "last_name": "Lovelace",
                "username": "ada123",
                "email": "ada@example.com",
                "phone_number": "+233501234567",
                "country": "GH",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("role", form.errors)

    def test_registration_accepts_selected_account_type(self):
        form = UserRegistrationForm(
            data={
                "first_name": "Ada",
                "last_name": "Lovelace",
                "username": "ada456",
                "email": "ada2@example.com",
                "phone_number": "+233501234567",
                "country": "GH",
                "role": "COACH",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            }
        )

        self.assertTrue(form.is_valid())

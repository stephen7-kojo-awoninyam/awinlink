from django.test import TestCase, override_settings
from django.urls import reverse
from django.db import IntegrityError, transaction

from accounts.forms import UserRegistrationForm
from accounts.models import User
from coaches.models import CoachProfile
from organizations.models import Organization
from scouts.models import ScoutProfile
from talents.models import TalentProfile


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

    def test_registration_rejects_username_with_different_case(self):
        User.objects.create_user(username="TakenHandle")
        form = UserRegistrationForm(
            data={
                "first_name": "Ada",
                "last_name": "Lovelace",
                "username": "@takenhandle",
                "email": "case-check@example.com",
                "phone_number": "+233501234567",
                "country": "GH",
                "role": "COACH",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("username", form.errors)

    def test_username_is_case_insensitively_unique_in_database(self):
        User.objects.create_user(username="UniqueHandle")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create_user(username="uniquehandle")


@override_settings(
    STORAGES={
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
)
class UsernameAvailabilityTests(TestCase):
    def test_registration_page_configures_username_availability_check(self):
        response = self.client.get(reverse("register"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'data-availability-url="/accounts/check-username/"',
        )

    def test_availability_check_accepts_prefixed_username(self):
        User.objects.create_user(username="TakenHandle")

        response = self.client.get(
            reverse("check_username"),
            {"username": "@takenhandle"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["available"])


@override_settings(
    STORAGES={
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
)
class RegistrationProfileTests(TestCase):
    @staticmethod
    def registration_data(username, role):
        return {
            "first_name": "Ada",
            "last_name": "Lovelace",
            "username": username,
            "email": f"{username}@example.com",
            "phone_number": "+233501234567",
            "country": "GH",
            "role": role,
            "password1": "StrongPass123!",
            "password2": "StrongPass123!",
        }

    def test_public_registration_choices_exclude_admin(self):
        response = self.client.get(reverse("register"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {value for value, _ in response.context["form"].fields["role"].choices},
            {"ATHLETE", "ORGANIZATION", "SCOUT", "COACH"},
        )
        self.assertNotContains(response, 'value="ADMIN"')

    def test_registration_form_rejects_admin(self):
        form = UserRegistrationForm(
            data=self.registration_data("forged_admin", "ADMIN")
        )

        self.assertFalse(form.is_valid())
        self.assertIn("role", form.errors)
        self.assertFalse(User.objects.filter(username="forged_admin").exists())

    def test_web_registration_rejects_forged_admin_without_logging_in(self):
        response = self.client.post(
            reverse("register"),
            self.registration_data("forged_admin", "ADMIN"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("role", response.context["form"].errors)
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(Organization.objects.count(), 0)
        self.assertEqual(TalentProfile.objects.count(), 0)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_authenticated_web_registration_cannot_create_admin(self):
        user = User.objects.create_user(username="existing_talent", role="ATHLETE")
        self.client.force_login(user)

        response = self.client.post(
            reverse("register"),
            self.registration_data("forged_admin", "ADMIN"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("role", response.context["form"].errors)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_existing_admin_can_still_log_in_and_access_dashboard(self):
        admin = User.objects.create_user(
            username="existing_admin", password="StrongPass123!", role="ADMIN"
        )

        response = self.client.post(
            reverse("login"),
            {"username": admin.username, "password": "StrongPass123!"},
        )

        self.assertRedirects(response, reverse("dashboard"))
        dashboard_response = self.client.get(reverse("dashboard"))
        self.assertTemplateUsed(dashboard_response, "dashboard/admin_dashboard.html")
        admin.refresh_from_db()
        self.assertEqual(admin.role, "ADMIN")
        self.assertTrue(admin.is_active)

    def test_api_registration_still_rejects_admin(self):
        response = self.client.post(
            "/api/auth/register/",
            self.registration_data("forged_api_admin", "ADMIN"),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("role", response.json())
        self.assertEqual(User.objects.count(), 0)

    def test_athlete_registration_creates_talent_profile(self):
        response = self.client.post(
            reverse("register"),
            self.registration_data("athlete123", "ATHLETE"),
        )

        self.assertRedirects(
            response,
            reverse("select_talent_category"),
        )
        self.assertTrue(
            TalentProfile.objects.filter(
                user__username="athlete123"
            ).exists()
        )

    def test_coach_registration_uses_coach_profile_and_category(self):
        response = self.client.post(
            reverse("register"),
            self.registration_data("coach123", "COACH"),
        )

        self.assertRedirects(
            response,
            reverse("select_coach_category"),
        )
        coach_user = User.objects.get(username="coach123")
        self.assertFalse(
            TalentProfile.objects.filter(user=coach_user).exists()
        )

        response = self.client.post(
            reverse("select_coach_category"),
            {"coach_category": "ARTS"},
        )
        self.assertRedirects(
            response,
            reverse("create_coach_profile"),
        )
        self.assertTrue(
            CoachProfile.objects.filter(
                user=coach_user,
                coach_category="ARTS",
            ).exists()
        )

        TalentProfile.objects.create(user=coach_user)
        response = self.client.get(reverse("coach_profile"))
        self.assertContains(response, "Coach - Arts")

    def test_scout_registration_uses_scout_profile_and_category(self):
        response = self.client.post(
            reverse("register"),
            self.registration_data("scout123", "SCOUT"),
        )

        self.assertRedirects(
            response,
            reverse("select_scout_category"),
        )
        scout_user = User.objects.get(username="scout123")
        self.assertFalse(
            TalentProfile.objects.filter(user=scout_user).exists()
        )

        response = self.client.post(
            reverse("select_scout_category"),
            {"scout_category": "SPORTS"},
        )
        self.assertRedirects(
            response,
            reverse("create_scout_profile"),
        )
        self.assertTrue(
            ScoutProfile.objects.filter(
                user=scout_user,
                scout_category="SPORTS",
            ).exists()
        )

        TalentProfile.objects.create(user=scout_user)
        response = self.client.get(reverse("create_scout_profile"))
        self.assertContains(response, "Sports Scout")

    def test_organization_registration_uses_organization_profile(self):
        data = self.registration_data("organization123", "ORGANIZATION")
        data.update(
            {
                "organization_name": "North Star Club",
                "organization_username": "northstarclub",
                "organization_email": "contact@northstar.example",
            }
        )
        response = self.client.post(reverse("register"), data)

        self.assertRedirects(
            response,
            reverse("dashboard"),
            fetch_redirect_response=False,
        )
        organization_user = User.objects.get(username="organization123")
        self.assertFalse(
            TalentProfile.objects.filter(user=organization_user).exists()
        )
        organization = Organization.objects.get(user=organization_user)
        TalentProfile.objects.create(user=organization_user)
        response = self.client.get(
            reverse("organization_profile", args=[organization.pk])
        )
        self.assertContains(response, "North Star Club")
        self.assertContains(response, "Organization")

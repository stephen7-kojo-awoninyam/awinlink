from django.test import TestCase
from django.urls import reverse

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

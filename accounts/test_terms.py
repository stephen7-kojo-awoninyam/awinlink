from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from accounts.forms import UserRegistrationForm
from accounts.legal import TERMS_VERSION
from organizations.models import Organization
from talents.models import TalentProfile


@override_settings(AUTH_RATE_LIMITS={'registration': {'ip': (200, 3600)}, 'login': {'ip': (60, 900), 'identity': (10, 900)}}, STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class TermsRegistrationTests(TestCase):
    def payload(self, role="ATHLETE"):
        return dict(first_name="Ada", last_name="Lovelace", username="newmember", email="ada@example.com",
            phone_number="+233501234567", country="GH", role=role,
            password1="StrongPass123!", password2="StrongPass123!", terms_accepted=True,
            terms_version=TERMS_VERSION, organization_name="Club", organization_username="club",
            organization_email="club@example.com")

    def test_missing_false_or_malformed_acceptance_never_creates_account(self):
        for value in (None, False, "false", "0", "off", "no", "anything", [], {}):
            for path in (reverse("register"), "/api/auth/register/"):
                with self.subTest(value=value, path=path):
                    data = self.payload()
                    if value is None:
                        del data["terms_accepted"]
                    else:
                        data["terms_accepted"] = value
                    if path.startswith("/api/"):
                        response = APIClient().post(path, data, format="json")
                        self.assertEqual(response.status_code, 400)
                        self.assertIn("terms_accepted", response.data)
                    elif not isinstance(value, (dict, list)):
                        response = self.client.post(path, data)
                        self.assertIn("terms_accepted", response.context["form"].errors)
                    self.assertFalse(get_user_model().objects.exists())

    def test_missing_or_outdated_version_rejected(self):
        for version in (None, "old-version"):
            data = self.payload()
            if version is None:
                del data["terms_version"]
            else:
                data["terms_version"] = version
            form = UserRegistrationForm(data)
            self.assertFalse(form.is_valid())
            self.assertIn("terms_version", form.errors)
            response = APIClient().post("/api/auth/register/", data, format="json")
            self.assertEqual(response.status_code, 400)
            self.assertFalse(get_user_model().objects.exists())

    def test_api_roles_record_server_time_and_preserve_profiles_and_tokens(self):
        for role in ("ATHLETE", "ORGANIZATION", "SCOUT", "COACH"):
            with self.subTest(role=role):
                data = self.payload(role)
                data["username"] = role.lower()
                data["organization_username"] = f"club_{role.lower()}"
                data["terms_accepted_at"] = "2000-01-01T00:00:00Z"
                data["terms_accepted_version"] = "forged"
                before = timezone.now()
                response = APIClient().post("/api/auth/register/", data, format="json")
                self.assertEqual(response.status_code, 201, response.data)
                user = get_user_model().objects.get(username=role.lower())
                self.assertEqual(user.terms_accepted_version, TERMS_VERSION)
                self.assertGreaterEqual(user.terms_accepted_at, before)
                self.assertLessEqual(user.terms_accepted_at, timezone.now())
                self.assertIn("access", response.data)
                self.assertIn("refresh", response.data)
                self.assertEqual(TalentProfile.objects.filter(user=user).exists(), role == "ATHLETE")
                self.assertEqual(Organization.objects.filter(user=user).exists(), role == "ORGANIZATION")

    def test_web_records_acceptance_and_preserves_session_and_redirect(self):
        data = self.payload()
        data["terms_accepted"] = "on"
        response = self.client.post(reverse("register"), data)
        self.assertRedirects(response, reverse("select_talent_category"), fetch_redirect_response=False)
        user = get_user_model().objects.get(username="newmember")
        self.assertEqual(user.terms_accepted_version, TERMS_VERSION)
        self.assertIsNotNone(user.terms_accepted_at)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_existing_user_login_does_not_fabricate_acceptance(self):
        user = get_user_model().objects.create_user(username="existing", password="StrongPass123!")
        response = APIClient().post("/api/auth/login/", {"username": user.username, "password": "StrongPass123!"})
        self.assertEqual(response.status_code, 200)
        web_response = self.client.post(reverse("login"), {"username": user.username, "password": "StrongPass123!"})
        self.assertRedirects(web_response, reverse("dashboard"), fetch_redirect_response=False)
        user.refresh_from_db()
        self.assertEqual(user.terms_accepted_version, "")
        self.assertIsNone(user.terms_accepted_at)

    def test_public_drafts_and_registration_links(self):
        for path in ("/terms/", "/privacy/", "/community-guidelines/"):
            response = self.client.get(path)
            self.assertContains(response, "Draft for legal review")
            self.assertContains(response, TERMS_VERSION)
            self.assertEqual(self.client.post(path).status_code, 405)
        response = self.client.get(reverse("register"))
        for path in ("/terms/", "/privacy/", "/community-guidelines/"):
            self.assertContains(response, f'href="{path}"')
        self.assertNotIn('checked', str(response.context["form"]["terms_accepted"]))


class TermsMigrationTests(TransactionTestCase):
    def test_existing_accounts_survive_with_no_inferred_acceptance(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        before = [("accounts", "0005_mobile_safety")]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(before)
        try:
            old_user = executor.loader.project_state(before).apps.get_model("accounts", "User")
            user = old_user.objects.create(username="pre_terms", password="!", role="ATHLETE")
            user_id = user.pk
        finally:
            MigrationExecutor(connection).migrate(latest)
        upgraded = get_user_model().objects.get(pk=user_id)
        self.assertEqual(upgraded.username, "pre_terms")
        self.assertEqual(upgraded.terms_accepted_version, "")
        self.assertIsNone(upgraded.terms_accepted_at)

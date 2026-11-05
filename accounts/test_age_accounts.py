"""Age boundaries, shared signup safeguards and verified guardian authorization."""
from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import AuthenticationFailed

from accounts.age_policy import (
    GUARDIAN_CONSENT_VERSION, account_capabilities, age_group, age_access_allowed,
    approve_guardian, revoke_guardian, verify_guardian,
)
from accounts.forms import UserRegistrationForm
from accounts.google_auth import digest
from accounts.legal import TERMS_VERSION
from accounts.models import GoogleAuthAttempt, GoogleIdentity, GuardianAuthorization, User
from accounts.tokens import AccountRefreshToken
from talents.models import TalentProfile


@override_settings(AUTH_RATE_LIMIT_CACHE_ALIAS="default", AUTH_RATE_LIMIT_REQUIRE_SHARED_CACHE=False)
class AgeAccountTests(TestCase):
    password = "AgeAccountPassword123!"

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def payload(self, **changes):
        return {"username": "young-member", "email": "child@example.invalid", "first_name": "Young",
                "last_name": "Member", "country": "GH", "phone_number": "+233501234567",
                "role": "ATHLETE", "password1": self.password, "password2": self.password,
                "terms_accepted": True, "terms_version": TERMS_VERSION,
                "date_of_birth": "2020-01-01", "guardian_email": "guardian@example.invalid", **changes}

    def child(self):
        response = APIClient().post("/api/auth/register/", self.payload(), format="json")
        self.assertEqual(response.status_code, 202, response.data)
        self.assertTrue(response.data["guardian_approval_required"])
        self.assertNotIn("access", response.data)
        self.assertNotIn("refresh", response.data)
        return User.objects.get(username="young-member")

    def guardian(self, **changes):
        return User.objects.create_user(**{"username": "guardian", "email": "guardian@example.invalid",
                                          "date_of_birth": date(1985, 1, 1), "password": self.password, **changes})

    def reviewer(self):
        reviewer = User.objects.create_user(username="reviewer", is_staff=True)
        reviewer.user_permissions.add(Permission.objects.get(codename="verify_guardianauthorization"))
        return reviewer

    def verify(self, child, guardian):
        return verify_guardian(actor=self.reviewer(), authorization_id=child.guardian_authorization.pk,
                               guardian_id=guardian.pk, reference="Reviewed case 123")

    def google_attempt(self, *, mobile=True, subject="young-google", email="child@example.invalid"):
        secret, handoff = "s" * 43, "h" * 43
        attempt = GoogleAuthAttempt.objects.create(
            state="state", nonce="", verifier="", status="VERIFIED",
            mobile_secret_hash=digest(secret) if mobile else "",
            mobile_handoff_hash=digest(handoff) if mobile else "",
            claims={"sub": subject, "email": email}, expires_at=timezone.now() + timedelta(minutes=10))
        return attempt, {"exchange_secret": secret, "handoff": handoff}

    def test_age_boundaries_and_leap_day(self):
        today = date(2026, 11, 4)
        for birth, expected in [(date(2013, 11, 5), "CHILD"), (date(2013, 11, 4), "TEEN"),
                                (date(2008, 11, 5), "TEEN"), (date(2008, 11, 4), "ADULT"), (None, "UNKNOWN")]:
            self.assertEqual(age_group(birth, today=today), expected)
        self.assertEqual(age_group(date(2008, 2, 29), today=date(2026, 2, 28)), "TEEN")
        self.assertEqual(age_group(date(2008, 2, 29), today=date(2026, 3, 1)), "ADULT")

    def test_web_and_api_require_valid_private_birth_date(self):
        for value in (None, "", "not-a-date", "2025-02-30", "2999-01-01", "1800-01-01"):
            data = self.payload(date_of_birth=value)
            if value is None:
                data.pop("date_of_birth")
            for web in (False, True):
                with self.subTest(value=value, web=web):
                    cache.clear()
                    response = self.client.post(reverse("register"), data) if web else APIClient().post("/api/auth/register/", data, format="json")
                    errors = response.context["form"].errors if web else response.data
                    self.assertIn("date_of_birth", errors)
                    self.assertFalse(User.objects.exists())

    def test_guardian_nomination_is_required_separate_and_does_not_grant_authority(self):
        for value in ("", "not-email", "CHILD@example.invalid"):
            form = UserRegistrationForm(self.payload(guardian_email=value))
            self.assertFalse(form.is_valid())
            self.assertIn("guardian_email", form.errors)
        for field in ("is_active", "is_staff", "is_superuser", "guardian_id", "guardian_approved", "age_group", "verified_at"):
            form = UserRegistrationForm(self.payload(**{field: True}))
            self.assertFalse(form.is_valid(), field)
        self.assertFalse(User.objects.exists())

    def test_pending_child_gets_no_web_session_and_cannot_login_or_refresh(self):
        response = self.client.post(reverse("register"), self.payload())
        self.assertEqual(response.status_code, 202)
        self.assertNotIn("_auth_user_id", self.client.session)
        child = User.objects.get(username="young-member")
        self.assertFalse(child.is_active)
        self.assertTrue(TalentProfile.objects.filter(user=child).exists())
        self.assertEqual(child.role, "ATHLETE")
        token = RefreshToken.for_user(child)  # Simulate a token minted by older code.
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION="Bearer " + str(token.access_token))
        for path in ("/api/auth/me/", "/api/messaging/conversations/", "/api/learning/courses/"):
            self.assertEqual(api.get(path).status_code, 401)
        result = APIClient().post("/api/auth/login/", {"username": child.username, "password": self.password})
        self.assertEqual(result.status_code, 401)
        result = APIClient().post("/api/auth/refresh/", {"refresh": str(token)})
        self.assertEqual(result.status_code, 401)
        self.client.post(reverse("login"), {"username": child.username, "password": self.password})
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_enabling_is_active_alone_does_not_bypass_approval(self):
        child = self.child()
        child.is_active = True
        child.save(update_fields=["is_active"])
        with self.assertRaises(AuthenticationFailed) as error:
            AccountRefreshToken.for_user(child)
        self.assertIn("guardian", str(error.exception))
        token = RefreshToken.for_user(child)
        token["guardian_approved"] = True
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION="Bearer " + str(token.access_token))
        self.assertEqual(api.get("/api/auth/me/").status_code, 401)
        self.client.force_login(child)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 403)
        from learning.classroom_signaling import credential_valid
        self.assertFalse(credential_valid(child.pk, session_key=self.client.session.session_key))

    def test_only_independent_reviewer_can_verify_then_only_bound_guardian_can_consent(self):
        child, guardian = self.child(), self.guardian()
        item = child.guardian_authorization
        for actor in (guardian, User.objects.create_user("role-admin", role="ADMIN")):
            with self.assertRaises(PermissionDenied):
                verify_guardian(actor=actor, authorization_id=item.pk, guardian_id=guardian.pk, reference="case")
        with self.assertRaises(PermissionDenied):
            approve_guardian(actor=guardian, authorization_id=item.pk, accepted=True, version=GUARDIAN_CONSENT_VERSION)
        self.verify(child, guardian)
        child.refresh_from_db()
        self.assertFalse(child.is_active)  # Verification is not consent.
        for accepted, version in ((False, GUARDIAN_CONSENT_VERSION), ("true", GUARDIAN_CONSENT_VERSION), (True, "old")):
            with self.assertRaises(ValidationError):
                approve_guardian(actor=guardian, authorization_id=item.pk, accepted=accepted, version=version)
        other = User.objects.create_user("other", date_of_birth=date(1990, 1, 1))
        with self.assertRaises(PermissionDenied):
            approve_guardian(actor=other, authorization_id=item.pk, accepted=True, version=GUARDIAN_CONSENT_VERSION)
        approve_guardian(actor=guardian, authorization_id=item.pk, accepted=True, version=GUARDIAN_CONSENT_VERSION)
        child.refresh_from_db()
        self.assertTrue(child.is_active)
        self.assertTrue(age_access_allowed(child))
        self.assertEqual(list(item.audit_events.values_list("action", flat=True)), ["REQUESTED", "VERIFIED", "APPROVED"])
        self.assertEqual(guardian.role, "ATHLETE")
        self.assertFalse(guardian.is_staff)
        self.assertEqual(APIClient().post("/api/auth/login/", {"username": child.username, "password": self.password}).status_code, 200)

    def test_teen_unknown_inactive_and_mismatched_guardians_cannot_be_verified(self):
        child, guardian = self.child(), self.guardian()
        reviewer = self.reviewer()
        for changes in ({"date_of_birth": date(2020, 1, 1)}, {"date_of_birth": None},
                        {"is_active": False}, {"email": "different@example.invalid"}):
            User.objects.filter(pk=guardian.pk).update(date_of_birth=date(1985, 1, 1), is_active=True,
                                                     email="guardian@example.invalid")
            User.objects.filter(pk=guardian.pk).update(**changes)
            with self.assertRaises((PermissionDenied, ValidationError)):
                verify_guardian(actor=reviewer, authorization_id=child.guardian_authorization.pk,
                                guardian_id=guardian.pk, reference="case")

    def test_guardian_api_and_web_are_scoped_and_require_explicit_consent_and_csrf(self):
        child, guardian = self.child(), self.guardian()
        self.verify(child, guardian)
        item = child.guardian_authorization
        api = APIClient()
        api.force_authenticate(guardian)
        self.assertEqual(api.get("/api/auth/guardians/").data[0]["id"], item.pk)
        self.assertEqual(api.post(f"/api/auth/guardians/{item.pk}/", {"action": "approve"}, format="json").status_code, 400)
        other = self.guardian(username="another", email="another@example.invalid")
        api.force_authenticate(other)
        self.assertEqual(api.get("/api/auth/guardians/").data, [])
        self.assertEqual(api.post(f"/api/auth/guardians/{item.pk}/", {"action": "approve"}, format="json").status_code, 404)
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(guardian)
        self.assertEqual(browser.post(reverse("guardian_authorizations"), {"authorization_id": item.pk, "action": "approve"}).status_code, 403)
        page = browser.get(reverse("guardian_authorizations"))
        self.assertContains(page, "I explicitly approve")
        response = browser.post(reverse("guardian_authorizations"), {"authorization_id": item.pk, "action": "approve",
            "accepted": "on", "version": GUARDIAN_CONSENT_VERSION, "csrfmiddlewaretoken": browser.cookies["csrftoken"].value})
        self.assertEqual(response.status_code, 302)

    def test_revocation_rejects_existing_tokens_sessions_and_reapproval(self):
        child, guardian = self.child(), self.guardian()
        item = self.verify(child, guardian)
        approve_guardian(actor=guardian, authorization_id=item.pk, accepted=True, version=GUARDIAN_CONSENT_VERSION)
        child.refresh_from_db()
        token = AccountRefreshToken.for_user(child)
        self.client.force_login(child)
        revoke_guardian(actor=guardian, authorization_id=item.pk)
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION="Bearer " + str(token.access_token))
        self.assertEqual(api.get("/api/auth/me/").status_code, 401)
        self.assertEqual(APIClient().post("/api/auth/refresh/", {"refresh": str(token)}).status_code, 401)
        self.assertEqual(self.client.get(reverse("guardian_authorizations")).status_code, 302)
        with self.assertRaises(ValidationError):
            approve_guardian(actor=guardian, authorization_id=item.pk, accepted=True, version=GUARDIAN_CONSENT_VERSION)

    def test_google_mobile_child_has_identity_but_no_credentials_or_approval(self):
        attempt, body = self.google_attempt()
        data = self.payload()
        for changes in ({"date_of_birth": ""}, {"guardian_email": ""}, {"guardian_approved": True}):
            response = APIClient().post("/api/auth/google/complete/", {**body, "signup": {**data, **changes}}, format="json")
            self.assertEqual(response.status_code, 400)
            self.assertFalse(User.objects.exists())
        response = APIClient().post("/api/auth/google/complete/", {**body, "signup": data}, format="json")
        self.assertEqual(response.status_code, 202)
        self.assertNotIn("access", response.data)
        child = User.objects.get(username="young-member")
        self.assertFalse(child.is_active)
        self.assertFalse(child.has_usable_password())
        self.assertTrue(GoogleIdentity.objects.filter(user=child).exists())
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "CONSUMED")
        self.assertEqual(attempt.claims, {})

    def test_guardian_deletion_preserves_child_but_withdraws_authorization(self):
        child, guardian = self.child(), self.guardian()
        item = self.verify(child, guardian)
        approve_guardian(actor=guardian, authorization_id=item.pk, accepted=True, version=GUARDIAN_CONSENT_VERSION)
        guardian.delete()
        child.refresh_from_db()
        item.refresh_from_db()
        self.assertFalse(child.is_active)
        self.assertEqual(item.status, "REVOKED")
        self.assertIsNone(item.guardian_id)
        self.assertFalse(age_access_allowed(child))

    def test_admin_verification_workflow_requires_review_and_does_not_activate_child(self):
        child, guardian = self.child(), self.guardian()
        reviewer = self.reviewer()
        self.client.force_login(reviewer)
        item = child.guardian_authorization
        self.assertEqual(self.client.get(reverse("admin:accounts_guardianauthorization_changelist")).status_code, 200)
        url = reverse("admin:accounts_guardian_verify", args=[item.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        result = self.client.post(url, {"guardian": guardian.pk, "reference": "case-verified"})
        self.assertEqual(result.status_code, 200)
        item.refresh_from_db()
        self.assertIsNone(item.verified_at)
        result = self.client.post(url, {"guardian": guardian.pk, "reference": "case-verified", "checked": "on"})
        self.assertEqual(result.status_code, 302)
        item.refresh_from_db()
        child.refresh_from_db()
        self.assertEqual(item.guardian_id, guardian.pk)
        self.assertEqual(item.verified_by_id, reviewer.pk)
        self.assertFalse(child.is_active)

    def test_google_existing_child_stays_pending_then_signs_in_only_after_approval(self):
        child = self.child()
        GoogleIdentity.objects.create(user=child, subject="young-google")
        _, body = self.google_attempt()
        result = APIClient().post("/api/auth/google/complete/", body, format="json")
        self.assertEqual(result.status_code, 202)
        self.assertNotIn("access", result.data)
        guardian = self.guardian()
        item = self.verify(child, guardian)
        approve_guardian(actor=guardian, authorization_id=item.pk, accepted=True, version=GUARDIAN_CONSENT_VERSION)
        GoogleAuthAttempt.objects.all().delete()
        _, body = self.google_attempt()
        result = APIClient().post("/api/auth/google/complete/", body, format="json")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["user"]["account_capabilities"]["age_group"], "CHILD")
        self.assertIn("access", result.data)

    def test_declaring_existing_account_as_child_restricts_its_old_credentials(self):
        user = User.objects.create_user("legacy-child", email="legacy-child@example.invalid")
        token = AccountRefreshToken.for_user(user)
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION="Bearer " + str(token.access_token))
        result = api.post("/api/auth/age-details/", {"date_of_birth": "2020-01-01",
                         "guardian_email": "guardian@example.invalid"}, format="json")
        self.assertEqual(result.status_code, 202)
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertEqual(api.get("/api/auth/me/").status_code, 401)
        self.assertTrue(GuardianAuthorization.objects.filter(child=user, status="PENDING").exists())

    def test_public_serializers_do_not_expose_age_or_guardian_information(self):
        from api.serializers import PublicUserSerializer
        child = self.child()
        public = PublicUserSerializer(child).data
        self.assertFalse({"date_of_birth", "birth_date_source", "account_capabilities", "guardian_email", "guardian"}.intersection(public))

    def test_google_web_child_does_not_receive_browser_session(self):
        attempt, _ = self.google_attempt(mobile=False)
        session = self.client.session
        session["google_verified"] = attempt.state
        session.save()
        response = self.client.post(reverse("google_complete"), self.payload())
        self.assertEqual(response.status_code, 202)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotIn("google_verified", self.client.session)

    def test_teen_adult_and_legacy_capabilities_preserve_roles_and_private_data(self):
        for birth_date, group in (("2010-01-01", "TEEN"), ("1990-01-01", "ADULT")):
            response = APIClient().post("/api/auth/register/", self.payload(username=group, date_of_birth=birth_date), format="json")
            self.assertEqual(response.status_code, 201, response.data)
            self.assertEqual(response.data["user"]["role"], "ATHLETE")
            self.assertEqual(response.data["user"]["account_capabilities"]["age_group"], group)
            self.assertNotIn("date_of_birth", response.data["user"])
        for role in ("ATHLETE", "ORGANIZATION", "SCOUT", "COACH", "ADMIN"):
            user = User.objects.create_user(username="legacy-" + role, role=role, password=self.password)
            self.assertEqual(account_capabilities(user)["age_group"], "UNKNOWN")
            self.assertTrue(account_capabilities(user)["can_access_account"])
            result = APIClient().post("/api/auth/login/", {"username": user.username, "password": self.password})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.data["user"]["role"], role)

    def test_age_details_are_one_time_and_cannot_unlock_known_child(self):
        adult = User.objects.create_user("existing-guardian", email="existing@example.invalid")
        api = APIClient()
        api.force_authenticate(adult)
        result = api.post("/api/auth/age-details/", {"date_of_birth": "1985-01-01"}, format="json")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["account_capabilities"]["age_group"], "ADULT")
        self.assertEqual(api.post("/api/auth/age-details/", {"date_of_birth": "2000-01-01"}, format="json").status_code, 400)
        child = self.child()
        api.force_authenticate(child)
        result = api.post("/api/auth/age-details/", {"date_of_birth": "1985-01-01"}, format="json")
        self.assertEqual(result.status_code, 400)
        child.refresh_from_db()
        self.assertEqual(child.age_group, "CHILD")

    def test_database_rejects_approval_without_verification_and_registration_is_atomic(self):
        child = self.child()
        with self.assertRaises(IntegrityError), transaction.atomic():
            GuardianAuthorization.objects.filter(child=child).update(status="APPROVED")
        form = UserRegistrationForm(self.payload(username="rollback", email="rollback@example.invalid"))
        self.assertTrue(form.is_valid(), form.errors)
        with patch("accounts.forms.create_guardian_request", side_effect=RuntimeError("unavailable")):
            with self.assertRaises(RuntimeError):
                form.save()
        self.assertFalse(User.objects.filter(username="rollback").exists())


class AgeMigrationTests(TransactionTestCase):
    def test_existing_roles_flags_and_age_unknown_survive(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        before = [("accounts", "0007_google_auth")]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(before)
        try:
            old = executor.loader.project_state(before).apps.get_model("accounts", "User")
            user = old.objects.create(username="age-migration", role="ADMIN", is_staff=True, is_active=True)
            user_id = user.pk
        finally:
            MigrationExecutor(connection).migrate(latest)
        user = User.objects.get(pk=user_id)
        self.assertEqual(user.age_group, "UNKNOWN")
        self.assertEqual(user.role, "ADMIN")
        self.assertTrue(user.is_staff and user.is_active)
        self.assertEqual(user.birth_date_source, "")

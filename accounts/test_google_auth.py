import time
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.google_auth import GoogleAuthError, begin, complete, digest, exchange, validate_id_token
from accounts.legal import TERMS_VERSION
from accounts.models import GoogleAuthAttempt, GoogleIdentity, User
from organizations.models import Organization
from talents.models import TalentProfile

HANDOFF = "h" * 43

CONFIG = dict(GOOGLE_OAUTH_CLIENT_ID="client.apps.googleusercontent.com", GOOGLE_OAUTH_CLIENT_SECRET="server-only",
    GOOGLE_OAUTH_REDIRECT_URI="https://awinlink.example/accounts/google/callback/",
    STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
              "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})


@override_settings(**CONFIG)
class GoogleTokenValidationTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def claims(self, **changes):
        now = int(time.time())
        return dict(iss="https://accounts.google.com", aud=CONFIG["GOOGLE_OAUTH_CLIENT_ID"],
            exp=now + 300, iat=now, sub="google-subject", nonce="nonce", email="person@example.com",
            email_verified=True, **changes) if not changes else {**self.claims(), **changes}

    def validate(self, claims, key=None, algorithm="RS256"):
        token = jwt.encode(claims, key or self.key, algorithm=algorithm, headers={"kid": "test"})
        with patch("accounts.google_auth.JWKS.get_signing_key_from_jwt", return_value=SimpleNamespace(key=self.key.public_key())):
            return validate_id_token(token, "nonce")

    def test_valid_signed_token(self):
        self.assertEqual(self.validate(self.claims())["sub"], "google-subject")

    def test_rejects_bad_signature_algorithm_issuer_audience_nonce_and_expiry(self):
        invalid = [dict(iss="https://attacker.example"), dict(aud="other-client"), dict(nonce="wrong"),
            dict(exp=int(time.time()) - 1), dict(iat=int(time.time()) + 600), dict(email_verified=False),
            dict(email_verified="true"), dict(email="not-an-email"), dict(sub=""), dict(azp="attacker"),
            dict(aud=[CONFIG["GOOGLE_OAUTH_CLIENT_ID"], "other"])]
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(GoogleAuthError):
                self.validate(self.claims(**changes))
        with self.assertRaises(GoogleAuthError):
            self.validate(self.claims(), key=self.other_key)
        with self.assertRaises(GoogleAuthError):
            self.validate(self.claims(), key="x" * 32, algorithm="HS256")
        for field in ("nonce", "sub", "exp", "iat", "email_verified"):
            claims = self.claims()
            del claims[field]
            with self.subTest(field=field), self.assertRaises(GoogleAuthError):
                self.validate(claims)


@override_settings(**CONFIG)
class GoogleFlowTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def claims(self, subject="subject", email="google@example.com"):
        return {"sub": subject, "email": email, "given_name": "Ada", "family_name": "Lovelace"}

    def verified(self, mobile=True, subject="subject", email="google@example.com"):
        attempt, _, secret = begin(mobile=mobile)
        attempt.status = "VERIFIED"
        attempt.claims = self.claims(subject, email)
        attempt.mobile_handoff_hash = digest(HANDOFF) if mobile else ""
        attempt.save()
        return attempt, secret

    def signup(self, role="ATHLETE"):
        return dict(username="newmember", first_name="Ada", last_name="Lovelace", country="GH",
            phone_number="+233501234567", role=role, terms_accepted=True, terms_version=TERMS_VERSION,
            organization_name="Club", organization_username="club", organization_email="club@example.com")

    def test_start_uses_code_nonce_pkce_fixed_redirect_and_hashed_mobile_secret(self):
        attempt, url, secret = begin(mobile=True)
        query = parse_qs(urlsplit(url).query)
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["redirect_uri"], [CONFIG["GOOGLE_OAUTH_REDIRECT_URI"]])
        self.assertEqual(query["nonce"], [attempt.nonce])
        self.assertEqual(attempt.mobile_secret_hash, digest(secret))
        self.assertNotIn(secret, url)
        self.assertNotIn("server-only", url)

    def test_throttling_and_private_responses(self):
        client = APIClient()
        for _ in range(30):
            response = client.post("/api/auth/google/start/", {}, format="json")
            self.assertEqual(response.status_code, 200)
        response = client.post("/api/auth/google/start/", {}, format="json")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response["Referrer-Policy"], "no-referrer")

    def test_expired_attempt_cleanup_keeps_live_identity(self):
        from django.core.management import call_command
        from io import StringIO
        attempt, _ = self.verified()
        attempt.expires_at = timezone.now() - timedelta(seconds=1)
        attempt.save()
        live, _, _ = begin()
        call_command("clear_google_auth_attempts", stdout=StringIO())
        self.assertFalse(GoogleAuthAttempt.objects.filter(pk=attempt.pk).exists())
        self.assertTrue(GoogleAuthAttempt.objects.filter(pk=live.pk).exists())

    def test_callback_exchange_once_and_google_secrets_are_cleared(self):
        attempt, _, _ = begin(mobile=True)
        response = Mock()
        response.json.return_value = {"id_token": "signed-token"}
        with patch("accounts.google_auth.httpx.post", return_value=response) as post, patch("accounts.google_auth.validate_id_token", return_value=self.claims()):
            result = exchange(attempt.state, "authorization-code")
            self.assertEqual(post.call_args.kwargs["data"]["code_verifier"], attempt.verifier)
            self.assertEqual(result.status, "VERIFIED")
            self.assertEqual(result.verifier, "")
            with self.assertRaises(GoogleAuthError):
                exchange(attempt.state, "authorization-code")
            self.assertEqual(post.call_count, 1)

    def test_mobile_callback_returns_only_fixed_app_uri_and_never_a_browser_session(self):
        attempt, _ = self.verified()
        with patch("accounts.google_views.exchange", return_value=attempt):
            response = self.client.get(reverse("google_callback"), {"state": attempt.state, "code": "code", "next": "https://attacker.example"})
        self.assertEqual(response.status_code, 302)
        returned = urlsplit(response["Location"])
        self.assertEqual((returned.scheme, returned.netloc, returned.path), ("awinlink", "google-complete", ""))
        handoff = parse_qs(returned.query)["handoff"][0]
        attempt.refresh_from_db()
        self.assertEqual(attempt.mobile_handoff_hash, digest(handoff))
        self.assertNotIn("access", response["Location"])
        self.assertNotIn("refresh", response["Location"])
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_web_callback_preserves_session_binding_and_requires_completion_post(self):
        attempt, _ = self.verified(mobile=False)
        session = self.client.session
        session["google_state"] = attempt.state
        session.save()
        with patch("accounts.google_views.exchange", return_value=attempt):
            response = self.client.get(reverse("google_callback"), {"state": attempt.state, "code": "code"})
        self.assertRedirects(response, reverse("google_complete"), fetch_redirect_response=False)
        self.assertEqual(self.client.session["google_verified"], attempt.state)
        self.assertNotIn("_auth_user_id", self.client.session)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.cookies = self.client.cookies
        self.assertEqual(csrf_client.post(reverse("google_complete"), self.signup()).status_code, 403)

    def test_registration_race_rolls_back_user_and_profiles(self):
        _, secret = self.verified()
        with patch("accounts.google_auth.GoogleIdentity.objects.create", side_effect=IntegrityError("race")):
            response = APIClient().post("/api/auth/google/complete/", {"exchange_secret": secret, "handoff": HANDOFF, "signup": self.signup()}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.exists())
        self.assertFalse(TalentProfile.objects.exists())

    def test_provider_tokens_or_posted_profiles_cannot_bypass_callback(self):
        result = APIClient().post("/api/auth/google/complete/", {"id_token": "untrusted", "email": "google@example.com", "signup": self.signup()}, format="json")
        self.assertEqual(result.status_code, 400)
        self.assertFalse(User.objects.exists())

    def test_mobile_requires_both_initiating_secret_and_browser_handoff(self):
        user = User.objects.create_user(username="established")
        GoogleIdentity.objects.create(user=user, subject="subject")
        _, secret = self.verified()
        client = APIClient()
        for data in ({"exchange_secret": secret}, {"handoff": HANDOFF},
                     {"exchange_secret": secret, "handoff": "wrong" * 10}):
            response = client.post("/api/auth/google/complete/", data, format="json")
            self.assertEqual(response.status_code, 400)
            self.assertNotIn("access", response.data)
        response = client.post("/api/auth/google/complete/", {"exchange_secret": secret, "handoff": HANDOFF}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["id"], user.pk)

    def test_browser_state_is_bound_to_session_and_start_requires_csrf(self):
        attempt, _, _ = begin()
        with patch("accounts.google_views.exchange") as mocked:
            response = self.client.get(reverse("google_callback"), {"state": attempt.state, "code": "code"})
            self.assertEqual(response.status_code, 400)
            mocked.assert_not_called()
        self.assertEqual(Client(enforce_csrf_checks=True).post(reverse("google_start")).status_code, 403)
        self.assertEqual(self.client.get(reverse("google_start")).status_code, 405)

    def test_cancel_and_invalid_token_fail_closed(self):
        attempt, _, _ = begin()
        session = self.client.session
        session["google_state"] = attempt.state
        session.save()
        response = self.client.get(reverse("google_callback"), {"state": attempt.state, "error": "access_denied"})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("_auth_user_id", self.client.session)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "FAILED")
        attempt, _, _ = begin(mobile=True)
        response = Mock()
        response.json.return_value = {"id_token": "bad"}
        with patch("accounts.google_auth.httpx.post", return_value=response), patch("accounts.google_auth.validate_id_token", side_effect=GoogleAuthError("invalid")):
            with self.assertRaises(GoogleAuthError):
                exchange(attempt.state, "code")
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "FAILED")
        self.assertEqual(attempt.claims, {})

    def test_same_email_never_links_or_logs_in_existing_user(self):
        existing = User.objects.create_user(username="existing", email="GOOGLE@example.com", password="StrongPass123!")
        attempt, secret = self.verified()
        response = APIClient().post("/api/auth/google/complete/", {"exchange_secret": secret, "handoff": HANDOFF, "signup": self.signup()}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(GoogleIdentity.objects.exists())
        self.assertEqual(User.objects.count(), 1)
        existing.refresh_from_db()
        self.assertTrue(existing.check_password("StrongPass123!"))

    def test_all_signup_roles_and_terms_and_verified_email(self):
        for role in ("ATHLETE", "ORGANIZATION", "SCOUT", "COACH"):
            attempt, secret = self.verified(subject=role, email=f"{role}@example.com")
            client = APIClient()
            pending = client.post("/api/auth/google/complete/", {"exchange_secret": secret, "handoff": HANDOFF}, format="json")
            self.assertTrue(pending.data["signup_required"])
            data = self.signup(role)
            data.update(username=role.lower(), organization_username=f"club_{role.lower()}")
            for changes in ({"terms_accepted": False}, {"terms_version": "old"}, {"role": "ADMIN"}):
                invalid = client.post("/api/auth/google/complete/", {"exchange_secret": secret, "handoff": HANDOFF, "signup": {**data, **changes}}, format="json")
                self.assertEqual(invalid.status_code, 400, invalid.data)
            before = timezone.now()
            result = client.post("/api/auth/google/complete/", {"exchange_secret": secret, "handoff": HANDOFF, "signup": {**data, "email": "forged@example.com"}}, format="json")
            self.assertEqual(result.status_code, 200, result.data)
            user = User.objects.get(username=role.lower())
            self.assertEqual(user.email, f"{role.lower()}@example.com")
            self.assertFalse(user.has_usable_password())
            self.assertEqual(user.role, role)
            self.assertEqual(user.terms_accepted_version, TERMS_VERSION)
            self.assertGreaterEqual(user.terms_accepted_at, before)
            self.assertEqual(TalentProfile.objects.filter(user=user).exists(), role == "ATHLETE")
            self.assertEqual(Organization.objects.filter(user=user).exists(), role == "ORGANIZATION")
            self.assertIn("access", result.data)
            replay = client.post("/api/auth/google/complete/", {"exchange_secret": secret, "handoff": HANDOFF}, format="json")
            self.assertEqual(replay.status_code, 400)
            attempt.refresh_from_db()
            self.assertEqual(attempt.claims, {})

    def test_subject_login_preserves_role_terms_and_email_even_if_google_email_changes(self):
        user = User.objects.create_user(username="existing", email="original@example.com", role="COACH")
        GoogleIdentity.objects.create(user=user, subject="subject")
        _, secret = self.verified(email="changed@example.com")
        result = APIClient().post("/api/auth/google/complete/", {"exchange_secret": secret, "handoff": HANDOFF, "signup": {"role": "ADMIN", "terms_accepted": True}}, format="json")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["user"]["id"], user.pk)
        user.refresh_from_db()
        self.assertEqual(user.role, "COACH")
        self.assertEqual(user.email, "original@example.com")
        self.assertIsNone(user.terms_accepted_at)
        user.is_active = False
        user.save()
        _, secret = self.verified()
        self.assertEqual(APIClient().post("/api/auth/google/complete/", {"exchange_secret": secret, "handoff": HANDOFF}, format="json").status_code, 400)

    def test_expired_invalid_and_pending_mobile_exchange(self):
        attempt, secret = self.verified()
        attempt.expires_at = timezone.now() - timedelta(seconds=1)
        attempt.save()
        client = APIClient()
        for value in ("invalid", secret):
            self.assertEqual(client.post("/api/auth/google/complete/", {"exchange_secret": value, "handoff": HANDOFF}, format="json").status_code, 400)
        _, _, secret = begin(mobile=True)
        self.assertEqual(client.post("/api/auth/google/complete/", {"exchange_secret": secret, "handoff": HANDOFF}, format="json").data, {"pending": True})

    def test_explicit_link_requires_authentication_password_and_cannot_reassign_identity(self):
        user = User.objects.create_user(username="existing", password="StrongPass123!")
        client = APIClient()
        self.assertEqual(client.post("/api/auth/google/start/", {"link": True, "password": "StrongPass123!"}, format="json").status_code, 400)
        client.force_authenticate(user)
        self.assertEqual(client.post("/api/auth/google/start/", {"link": True, "password": "wrong"}, format="json").status_code, 400)
        response = client.post("/api/auth/google/start/", {"link": True, "password": "StrongPass123!"}, format="json")
        self.assertEqual(response.status_code, 200)
        attempt = GoogleAuthAttempt.objects.get(mobile_secret_hash=digest(response.data["exchange_secret"]))
        attempt.status = "VERIFIED"
        attempt.claims = self.claims()
        attempt.mobile_handoff_hash = digest(HANDOFF)
        attempt.save()
        result = client.post("/api/auth/google/complete/", {"exchange_secret": response.data["exchange_secret"], "handoff": HANDOFF}, format="json")
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(GoogleIdentity.objects.get(subject="subject").user_id, user.pk)
        self.assertTrue(user.has_usable_password())
        other = User.objects.create_user(username="other", password="StrongPass123!")
        attempt, secret = self.verified()
        attempt.link_user = other
        attempt.save()
        client.force_authenticate(other)
        self.assertEqual(client.post("/api/auth/google/complete/", {"exchange_secret": secret, "handoff": HANDOFF}, format="json").status_code, 400)
        self.assertEqual(GoogleIdentity.objects.get(subject="subject").user_id, user.pk)

    def test_web_signup_is_csrf_protected_and_routes_to_onboarding(self):
        attempt, _ = self.verified(mobile=False)
        session = self.client.session
        session["google_verified"] = attempt.state
        session.save()
        page = self.client.get(reverse("google_complete"))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, 'name="password1"')
        self.assertNotIn("_auth_user_id", self.client.session)
        result = self.client.post(reverse("google_complete"), self.signup())
        self.assertRedirects(result, reverse("select_talent_category"), fetch_redirect_response=False)
        self.assertIn("_auth_user_id", self.client.session)
        user = User.objects.get(username="newmember")
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.terms_accepted_version, TERMS_VERSION)

    @override_settings(GOOGLE_OAUTH_CLIENT_SECRET="")
    def test_unconfigured_fails_closed_without_creating_attempt(self):
        self.assertEqual(APIClient().post("/api/auth/google/start/", {}, format="json").status_code, 400)
        self.assertFalse(GoogleAuthAttempt.objects.exists())

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from .tokens import AccountRefreshToken


@override_settings(AUTH_RATE_LIMIT_CACHE_ALIAS="default", AUTH_RATE_LIMIT_REQUIRE_SHARED_CACHE=False)
class JwtLogoutTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="jwt-logout-owner", password="SafeTestPassword123!")
        self.other = get_user_model().objects.create_user(username="jwt-logout-other", password="SafeTestPassword123!")
        self.client = APIClient()
        self.refresh = AccountRefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.refresh.access_token}")

    def test_logout_blacklists_only_the_callers_refresh_token(self):
        response = self.client.post("/api/auth/logout/", {"refresh": str(self.refresh)}, format="json")
        self.assertEqual(response.status_code, 204)
        self.assertTrue(BlacklistedToken.objects.filter(token__jti=self.refresh["jti"]).exists())
        from .authentication import RevocableJWTAuthentication
        with self.assertRaises(AuthenticationFailed):
            RevocableJWTAuthentication().get_validated_token(str(self.refresh.access_token))
        self.assertEqual(self.client.post("/api/auth/refresh/", {"refresh": str(self.refresh)}, format="json").status_code, 401)

    def test_user_cannot_revoke_another_accounts_refresh_token(self):
        other_refresh = RefreshToken.for_user(self.other)
        response = self.client.post("/api/auth/logout/", {"refresh": str(other_refresh)}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(BlacklistedToken.objects.filter(token__jti=other_refresh["jti"]).exists())

    def test_logout_uses_authenticated_session_id_without_sending_refresh(self):
        response = self.client.post("/api/auth/logout/", {}, format="json")
        self.assertEqual(response.status_code, 204)
        self.assertTrue(BlacklistedToken.objects.filter(token__jti=self.refresh["jti"]).exists())

    def test_logout_requires_authentication_and_rejects_malformed_tokens(self):
        anonymous = APIClient().post("/api/auth/logout/", {"refresh": str(self.refresh)}, format="json")
        self.assertEqual(anonymous.status_code, 401)
        self.assertEqual(self.client.post("/api/auth/logout/", {"refresh": "not-a-jwt"}, format="json").status_code, 400)


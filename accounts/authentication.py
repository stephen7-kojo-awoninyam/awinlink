"""JWT authentication that immediately rejects access tokens from logged-out sessions."""
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from .token_revocation import refresh_session_revoked


class RevocableJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        from .age_policy import age_access_allowed, PENDING_MESSAGE
        if not age_access_allowed(user):
            raise AuthenticationFailed(PENDING_MESSAGE)
        return user

    def get_validated_token(self, raw_token):
        token = super().get_validated_token(raw_token)
        if refresh_session_revoked(token.get("sid")):
            raise AuthenticationFailed("This session has expired. Sign in again.")
        return token

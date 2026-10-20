from django.contrib.auth import get_user_model
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.utils import get_md5_hash_password
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from .security import RefreshThrottle
from .token_revocation import refresh_session_revoked


class AccountTokenRefreshView(TokenRefreshView):
    throttle_classes = [RefreshThrottle]


class AccountRefreshToken(RefreshToken):
    """Tie each access token to its revocable refresh-session JTI."""
    @property
    def access_token(self):
        access = super().access_token
        access['sid'] = self.payload[api_settings.JTI_CLAIM]
        return access


class AccountTokenRefreshSerializer(TokenRefreshSerializer):
    token_class = AccountRefreshToken

    def validate(self, attrs):
        try:
            token = self.token_class(attrs['refresh'])
        except TokenError:
            raise AuthenticationFailed('This session has expired. Sign in again.') from None
        user = get_user_model().objects.filter(pk=token.get(api_settings.USER_ID_CLAIM), is_active=True).first()
        if not user or token.get(api_settings.REVOKE_TOKEN_CLAIM) != get_md5_hash_password(user.password):
            raise AuthenticationFailed('This session has expired. Sign in again.')
        return super().validate(attrs)


class AccountTokenBlacklistView(APIView):
    """Revoke the authenticated device's refresh token during logout."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [RefreshThrottle]

    def post(self, request):
        has_refresh = hasattr(request.data, 'get') and 'refresh' in request.data
        value = request.data.get('refresh') if has_refresh else None
        if has_refresh:
            if not isinstance(value, str) or len(value) > 8192:
                return Response({'detail': 'A valid refresh token is required.'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                token = RefreshToken(value)
            except TokenError:
                return Response({'detail': 'This refresh token is invalid or expired.'}, status=status.HTTP_400_BAD_REQUEST)
            if str(token.get(api_settings.USER_ID_CLAIM, '')) != str(request.user.pk):
                return Response({'detail': 'This refresh token belongs to another account.'}, status=status.HTTP_403_FORBIDDEN)
            token.blacklist()
        else:
            # Bind logout to the access token's session id. This still revokes
            # the latest rotated refresh token after API middleware refreshes an
            # expired access token and avoids sending stale refresh credentials.
            session_id = request.auth.get('sid') if request.auth else None
            outstanding = OutstandingToken.objects.filter(jti=session_id, user=request.user).first()
            if outstanding is None:
                return Response({'detail': 'No revocable session was found.'}, status=status.HTTP_400_BAD_REQUEST)
            BlacklistedToken.objects.get_or_create(token=outstanding)
        return Response(status=status.HTTP_204_NO_CONTENT)

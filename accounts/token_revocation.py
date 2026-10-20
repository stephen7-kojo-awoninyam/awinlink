"""Small, view-independent helpers for checking revoked refresh sessions."""


def refresh_session_revoked(session_id):
    if not session_id:
        return False
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
    return BlacklistedToken.objects.filter(token__jti=session_id).exists()

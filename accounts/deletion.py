"""Own-account deletion; Google proof cannot be used for login, linking or another user."""
import secrets
from collections.abc import Mapping

from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from .age_policy import age_access_allowed
from .google_auth import GoogleAuthError, digest, require_recent_authentication
from .models import GoogleAuthAttempt, GoogleIdentity, User


class DeletionDenied(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


@transaction.atomic
def delete_own_account(*, user_id, password=None, google_proof=None, browser_state=None):
    # Match guardian transitions' lock order. Recheck current state, not request/token claims.
    user = User.objects.select_for_update().filter(pk=user_id).first()
    if not user or not user.is_active or not age_access_allowed(user):
        raise DeletionDenied("This account is unavailable or requires guardian approval.", 403)
    attempt = None
    if google_proof is not None or browser_state is not None:
        if browser_state is not None:
            attempt = GoogleAuthAttempt.objects.select_for_update().filter(
                state=browser_state, mobile_secret_hash="", purpose="DELETE", reauth_user=user).first()
        elif isinstance(google_proof, Mapping):
            secret, handoff = google_proof.get("exchange_secret"), google_proof.get("handoff")
            if isinstance(secret, str) and 32 <= len(secret) <= 128 and isinstance(handoff, str) and 32 <= len(handoff) <= 128:
                attempt = GoogleAuthAttempt.objects.select_for_update().filter(
                    mobile_secret_hash=digest(secret), purpose="DELETE", reauth_user=user).first()
                if attempt and (not attempt.mobile_handoff_hash or not secrets.compare_digest(attempt.mobile_handoff_hash, digest(handoff))):
                    attempt = None
        if (not attempt or attempt.purpose != "DELETE" or attempt.reauth_user_id != user.pk
            or attempt.link_user_id or attempt.status != "VERIFIED" or attempt.expires_at <= timezone.now()
            or not secrets.compare_digest(attempt.reauth_auth_hash, user.get_session_auth_hash())
            or not GoogleIdentity.objects.select_for_update().filter(user=user, subject=attempt.claims.get("sub")).exists()):
            raise DeletionDenied("Confirm deletion again using the Google account linked to this Awinlink account.")
        try:
            require_recent_authentication(attempt.claims)
        except GoogleAuthError as exc:
            raise DeletionDenied(str(exc)) from exc
    elif not isinstance(password, str) or not user.check_password(password):
        raise DeletionDenied("Enter your current password.")
    from organizations.models import Organization
    if Organization.objects.filter(user=user).exists():
        raise DeletionDenied("Transfer organization ownership before deleting your account.", 409)
    if attempt:
        attempt.status = "CONSUMED"
        attempt.claims = {}
        attempt.save(update_fields=["status", "claims"])
    # Existing model deletion signals and cascading guardian/identity cleanup still run.
    try:
        user.delete()
    except ProtectedError as exc:
        raise DeletionDenied('Shared learning or other protected records require support resolution before account deletion. No account has been deleted.', 409) from exc

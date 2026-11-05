"""Account age and guardian capabilities, independent of platform/classroom roles."""
from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

GUARDIAN_CONSENT_VERSION = "guardian-v1"
PENDING_MESSAGE = "This child account is restricted until a verified adult guardian approves it."


def age_group(birth_date, *, today=None):
    if birth_date is None:
        return "UNKNOWN"
    today = today or timezone.localdate()
    years = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    return "CHILD" if years < 13 else "TEEN" if years < 18 else "ADULT"


def validate_birth_date(value):
    today = timezone.localdate()
    if not isinstance(value, date) or value > today or today.year - value.year > 120:
        raise ValidationError("Enter a valid date of birth, no more than 120 years ago and not in the future.")
    return value


def guardian_approved(user):
    from .models import GuardianAuthorization
    # Current records, never a token claim or a caller-supplied account type.
    authorization = GuardianAuthorization.objects.filter(
        child_id=user.pk, status="APPROVED", guardian__is_active=True,
        verified_at__isnull=False, verified_by__isnull=False, consented_at__isnull=False,
        consent_version=GUARDIAN_CONSENT_VERSION, revoked_at__isnull=True,
    ).select_related("guardian").first()
    return bool(authorization and authorization.guardian.age_group == "ADULT")


def age_access_allowed(user):
    if user.age_group == "ADULT":
        return True
    # A pending/revoked child does not age out of the approval requirement silently.
    from .models import GuardianAuthorization
    has_request = GuardianAuthorization.objects.filter(child_id=user.pk).exists()
    return (user.age_group != "CHILD" and not has_request) or guardian_approved(user)


def account_capabilities(user):
    age_allowed = age_access_allowed(user)
    allowed = bool(user.is_active and age_allowed)
    return {
        "age_group": user.age_group,
        "guardian_approval_required": not age_allowed,
        "can_access_account": allowed,
        "can_manage_children": allowed and user.age_group == "ADULT",
        "protected_teen": user.age_group == "TEEN",
    }


def prepare_registration(user, cleaned_data):
    user.date_of_birth = validate_birth_date(cleaned_data["date_of_birth"])
    user.birth_date_source = "REGISTRATION"
    user.is_active = user.age_group != "CHILD"
    return user


def create_guardian_request(user, cleaned_data):
    if user.age_group == "CHILD":
        from .models import GuardianAuthorization, GuardianAuditEvent
        authorization = GuardianAuthorization.objects.create(
            child=user, nominated_email=cleaned_data["guardian_email"].strip().lower())
        GuardianAuditEvent.objects.create(authorization=authorization, action="REQUESTED")


def _locked(authorization_id):
    from .models import GuardianAuthorization, User
    # All transitions lock child, then authorization, in the same order.
    child_id = GuardianAuthorization.objects.get(pk=authorization_id).child_id
    child = User.objects.select_for_update().get(pk=child_id)
    authorization = GuardianAuthorization.objects.select_for_update().get(pk=authorization_id)
    return authorization, child


def _adult(actor):
    from .models import User
    current = User.objects.get(pk=actor.pk)
    if not current.is_active or current.age_group != "ADULT" or not age_access_allowed(current):
        raise PermissionDenied("An active adult account with a recorded date of birth is required.")
    return current


@transaction.atomic
def verify_guardian(*, actor, authorization_id, guardian_id, reference):
    """Trusted review of identity, adulthood AND relationship; email/OAuth alone is insufficient."""
    from .models import User, GuardianAuditEvent
    reviewer = User.objects.get(pk=actor.pk)
    if not reviewer.is_active or not reviewer.is_staff or not reviewer.has_perm("accounts.verify_guardianauthorization"):
        raise PermissionDenied("Guardian verification permission is required.")
    reference = reference.strip() if isinstance(reference, str) else ""
    if not reference or len(reference) > 200:
        raise ValidationError("Record a verification case reference (maximum 200 characters).")
    authorization, child = _locked(authorization_id)
    if child.age_group == "ADULT":
        raise PermissionDenied("Guardian authority cannot be established for an adult account.")
    guardian = _adult(User.objects.get(pk=guardian_id))
    if guardian.pk in {child.pk, reviewer.pk} or reviewer.pk == child.pk:
        raise PermissionDenied("The reviewer, guardian and child must be separate accounts.")
    if authorization.status != "PENDING" or authorization.verified_at:
        raise ValidationError("Only an unverified pending request can be verified.")
    if guardian.email.strip().lower() != authorization.nominated_email.lower():
        raise ValidationError("The guardian must match the nominated email address.")
    authorization.guardian = guardian
    authorization.verified_by = reviewer
    authorization.verified_at = timezone.now()
    authorization.verification_reference = reference
    authorization.save(update_fields=["guardian", "verified_by", "verified_at", "verification_reference"])
    GuardianAuditEvent.objects.create(authorization=authorization, actor=reviewer, action="VERIFIED")
    return authorization


@transaction.atomic
def approve_guardian(*, actor, authorization_id, accepted, version):
    from .models import GuardianAuditEvent
    authorization, child = _locked(authorization_id)
    if child.age_group == "ADULT":
        raise PermissionDenied("An adult account must complete its own account recovery.")
    guardian = _adult(actor)
    if authorization.guardian_id != guardian.pk or not authorization.verified_at or not authorization.verified_by_id:
        raise PermissionDenied("Only the verified guardian may approve this request.")
    if accepted is not True or version != GUARDIAN_CONSENT_VERSION:
        raise ValidationError("Explicit acceptance of the current guardian consent is required.")
    if authorization.status != "PENDING":
        raise ValidationError("This request is no longer pending.")
    authorization.status = "APPROVED"
    authorization.consented_at = timezone.now()
    authorization.consent_version = version
    authorization.save(update_fields=["status", "consented_at", "consent_version"])
    child.is_active = True
    child.save(update_fields=["is_active"])
    GuardianAuditEvent.objects.create(authorization=authorization, actor=guardian, action="APPROVED")
    return authorization


@transaction.atomic
def revoke_guardian(*, actor, authorization_id):
    from .models import GuardianAuditEvent, User
    authorization, child = _locked(authorization_id)
    if child.age_group == "ADULT":
        raise PermissionDenied("Guardian authority ends when the account holder turns 18.")
    guardian = User.objects.get(pk=actor.pk)
    if not guardian.is_active or guardian.pk != authorization.guardian_id:
        raise PermissionDenied("Only the linked guardian may withdraw this authorization.")
    if authorization.status == "REVOKED":
        return authorization
    authorization.status = "REVOKED"
    authorization.revoked_at = timezone.now()
    authorization.save(update_fields=["status", "revoked_at"])
    child.is_active = False
    child.save(update_fields=["is_active"])
    GuardianAuditEvent.objects.create(authorization=authorization, actor=guardian, action="REVOKED")
    from .guardian_permissions import restrict_live_access
    restrict_live_access(child.pk)
    return authorization

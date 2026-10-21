"""Roster transitions lock organization then affiliation and retain every decision."""
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError

from talents.models import TalentProfile
from .models import Organization, OrganizationTalent, OrganizationTalentEvent
from .permissions import require_organization_capability, OrganizationCapability as Cap


def require_manager(user, organization):
    require_organization_capability(user, organization, Cap.MANAGE_RECRUITMENT)


def linked_talent(username):
    talent = TalentProfile.objects.select_related("user").filter(user__username__iexact=username, user__is_active=True).first()
    if talent is None:
        raise ValidationError({"username": "Choose an active talent username."})
    return talent


def require_unblocked_link(actor, organization, talent):
    from accounts.models import UserBlock
    from django.db.models import Q
    peers = {actor.pk, organization.user_id} - {None, talent.user_id}
    if UserBlock.objects.filter(
        Q(user_id=talent.user_id, blocked_user_id__in=peers)
        | Q(blocked_user_id=talent.user_id, user_id__in=peers)
    ).exists():
        raise PermissionDenied("This account cannot receive an affiliation request from this organization.")


def record(entry, actor, action, reason=""):
    OrganizationTalentEvent.objects.create(affiliation=entry, actor=actor, action=action, reason=reason)


@transaction.atomic
def create_entry(organization_id, actor, data):
    organization = Organization.objects.select_for_update().get(pk=organization_id)
    require_manager(actor, organization)
    username = data.pop("username", "")
    talent = linked_talent(username) if username else None
    if talent is not None:
        require_unblocked_link(actor, organization, talent)
    try:
        with transaction.atomic():
            entry = OrganizationTalent.objects.create(organization=organization, talent=talent,
                status="PENDING" if talent else "UNCLAIMED", **data)
    except IntegrityError:
        raise ValidationError("This active tag already exists in this roster.") from None
    record(entry, actor, "REQUESTED" if talent else "CREATED")
    return entry


@transaction.atomic
def transition(entry_id, actor, action, username="", reason=""):
    organization_id = OrganizationTalent.objects.values_list("organization_id", flat=True).get(pk=entry_id)
    organization = Organization.objects.select_for_update().get(pk=organization_id)
    # The talent join is nullable for unclaimed entries; PostgreSQL must lock
    # only the affiliation, not the nullable side of that outer join.
    entry = OrganizationTalent.objects.select_for_update(of=("self",)).select_related("talent").get(pk=entry_id)
    if not get_user_model().objects.filter(pk=actor.pk, is_active=True).exists():
        raise PermissionDenied("An active account is required.")
    recipient = entry.talent_id is not None and entry.talent.user_id == actor.pk
    if action in {"CONFIRM", "DECLINE"}:
        if not recipient:
            raise PermissionDenied("Only the linked talent can respond.")
        if organization.status != "ACTIVE" or entry.status != "PENDING":
            raise ValidationError("This request is no longer pending for an active organization.")
        entry.status = "CONFIRMED" if action == "CONFIRM" else "DECLINED"
    elif action == "LINK":
        require_manager(actor, organization)
        if entry.status != "UNCLAIMED":
            raise ValidationError("Only unclaimed entries can be linked.")
        entry.talent = linked_talent(username)
        require_unblocked_link(actor, organization, entry.talent)
        entry.status = "PENDING"
    elif action == "REMOVE":
        if not recipient:
            require_manager(actor, organization)
        if entry.status == "REMOVED":
            raise ValidationError("This entry was already removed.")
        entry.status = "REMOVED"
    else:
        raise ValidationError("Unknown roster action.")
    try:
        with transaction.atomic():
            entry.save(update_fields=["talent", "status", "updated_at"])
    except IntegrityError:
        raise ValidationError("This active tag already exists in this roster.") from None
    record(entry, actor, action, reason)
    return entry


def public_entries(user=None):
    rows = OrganizationTalent.objects.select_related("organization", "talent__user").filter(
        status="CONFIRMED", organization__status="ACTIVE", talent__profile_visibility="PUBLIC", talent__user__is_active=True)
    if user is not None and user.is_authenticated:
        from accounts.models import UserBlock
        from django.db.models import Q
        blocks = UserBlock.objects.filter(Q(user=user) | Q(blocked_user=user))
        ids = set(blocks.values_list("user_id", flat=True)) | set(blocks.values_list("blocked_user_id", flat=True))
        ids.discard(user.pk)
        rows = rows.exclude(talent__user_id__in=ids).exclude(organization__user_id__in=ids)
    return rows

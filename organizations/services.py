"""Organization team invitations and member management services.

The organization row is the shared lock for creation and every transition. On
databases with row locking this serializes invitations even before a row exists.
SQLite uses its write lock and may require callers to retry a lock error.
"""

from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import Organization, OrganizationMembership, OrganizationTeamInvitation
from .permissions import OrganizationCapability, require_organization_capability


TEAM_ROLES = frozenset({
    OrganizationMembership.Role.MANAGER,
    OrganizationMembership.Role.RECRUITER,
    OrganizationMembership.Role.VIEWER,
})


def _require_active_user(user):
    if (
        not getattr(user, "is_authenticated", False)
        or getattr(user, "pk", None) is None
        or not get_user_model().objects.filter(pk=user.pk, is_active=True).exists()
    ):
        raise PermissionDenied("An active user account is required.")


def _require_owner(user, organization):
    return require_organization_capability(
        user, organization, OrganizationCapability.MANAGE_MEMBERS,
    )


def _require_team_role(role):
    if role not in TEAM_ROLES:
        raise ValidationError({"role": "Invite a manager, recruiter, or viewer. Ownership requires a separate transfer."})


def _require_invitable_membership(organization, recipient):
    membership = OrganizationMembership.objects.select_for_update().filter(
        organization=organization, user=recipient,
    ).first()
    if membership is not None and membership.status != OrganizationMembership.Status.REMOVED:
        raise ValidationError("The recipient already has an active or suspended membership.")
    if organization.user_id == recipient.pk and not organization.memberships.exists():
        raise ValidationError("The organization's linked owner cannot be invited as a team member.")
    return membership


def _locked_invitation(invitation):
    invitation_id = getattr(invitation, "pk", invitation)
    # Read the organization id first so every operation takes locks in the same order.
    organization_id = OrganizationTeamInvitation.objects.values_list(
        "organization_id", flat=True,
    ).get(pk=invitation_id)
    organization = Organization.objects.select_for_update().get(pk=organization_id)
    current = OrganizationTeamInvitation.objects.select_for_update().get(
        pk=invitation_id, organization=organization,
    )
    return organization, current


def _require_pending(invitation):
    if invitation.status != OrganizationTeamInvitation.Status.PENDING:
        raise ValidationError("This invitation has already been used or closed.")
    if invitation.expires_at <= timezone.now():
        raise ValidationError("This invitation has expired.")


def _verify_recipient(invitation, recipient, token):
    _require_active_user(recipient)
    if invitation.recipient_id != recipient.pk:
        raise PermissionDenied("Only the invitation recipient can respond.")
    _require_pending(invitation)
    if not invitation.check_token(token):
        raise PermissionDenied("Invalid invitation token.")


def _transition(invitation, status):
    # A conditional write is also a guard against stale transitions on databases
    # where SELECT FOR UPDATE is unavailable. Membership writes roll back on failure.
    changed = OrganizationTeamInvitation.objects.filter(
        pk=invitation.pk, status=OrganizationTeamInvitation.Status.PENDING,
        expires_at__gt=timezone.now(),
    ).update(status=status, updated_at=timezone.now())
    if changed != 1:
        raise ValidationError("This invitation is no longer pending or has expired.")
    invitation.refresh_from_db()
    return invitation


@transaction.atomic
def create_team_invitation(*, organization, inviter, recipient, role="VIEWER", expires_at=None):
    """Return (invitation, raw_token); callers deliver the token without storing it."""
    organization = Organization.objects.select_for_update().get(pk=organization.pk)
    _require_owner(inviter, organization)
    _require_active_user(recipient)
    _require_team_role(role)
    _require_invitable_membership(organization, recipient)
    expires_at = expires_at if expires_at is not None else timezone.now() + timedelta(days=7)
    if not isinstance(expires_at, datetime) or timezone.is_naive(expires_at) or expires_at <= timezone.now():
        raise ValidationError({"expires_at": "Provide a future, timezone-aware expiry."})

    pending = OrganizationTeamInvitation.objects.filter(
        organization=organization, recipient=recipient,
        status=OrganizationTeamInvitation.Status.PENDING,
    )
    if pending.filter(expires_at__gt=timezone.now()).exists():
        raise ValidationError("A pending invitation already exists for this recipient.")
    pending.update(status=OrganizationTeamInvitation.Status.EXPIRED, updated_at=timezone.now())

    invitation = OrganizationTeamInvitation(
        organization=organization, inviter=inviter, recipient=recipient,
        role=role, expires_at=expires_at,
    )
    token = invitation.generate_token()
    invitation.full_clean()
    invitation.save()
    return invitation, token


@transaction.atomic
def accept_team_invitation(*, invitation, recipient, token):
    """Accept once and create or reactivate the recipient's membership atomically."""
    organization, invitation = _locked_invitation(invitation)
    _verify_recipient(invitation, recipient, token)
    # Invitations cannot outlive their inviter's authority to manage this team.
    _require_owner(invitation.inviter, organization)
    _require_team_role(invitation.role)
    membership = _require_invitable_membership(organization, recipient)

    # Preserve the legacy owner's access when adding the very first team member.
    # The permission resolver disables legacy fallback as soon as a roster exists.
    if not organization.memberships.exists():
        OrganizationMembership.objects.create(
            organization=organization, user_id=organization.user_id,
            role=OrganizationMembership.Role.OWNER,
        )
    if membership is None:
        OrganizationMembership.objects.create(
            organization=organization, user=recipient, role=invitation.role,
        )
    else:
        membership.role = invitation.role
        membership.status = OrganizationMembership.Status.ACTIVE
        membership.save(update_fields=["role", "status", "updated_at"])
    return _transition(invitation, OrganizationTeamInvitation.Status.ACCEPTED)


@transaction.atomic
def decline_team_invitation(*, invitation, recipient, token):
    """Decline once, without creating or changing memberships."""
    _, invitation = _locked_invitation(invitation)
    _verify_recipient(invitation, recipient, token)
    return _transition(invitation, OrganizationTeamInvitation.Status.DECLINED)


@transaction.atomic
def revoke_team_invitation(*, invitation, actor):
    """Allow the current organization owner to revoke a pending invitation."""
    organization, invitation = _locked_invitation(invitation)
    _require_owner(actor, organization)
    _require_pending(invitation)
    return _transition(invitation, OrganizationTeamInvitation.Status.REVOKED)


@transaction.atomic
def list_team_members(*, organization, actor):
    """Return the scoped roster, including suspended and removed memberships."""
    organization = Organization.objects.select_for_update().get(pk=organization.pk)
    _require_owner(actor, organization)
    # Evaluate inside the permission-checked transaction, rather than returning
    # a lazy queryset whose data is fetched after the owner check.
    return list(organization.memberships.select_related("user").order_by("pk"))


def _locked_team_member(organization, actor, membership):
    organization = Organization.objects.select_for_update().get(pk=organization.pk)
    _require_owner(actor, organization)
    membership_id = getattr(membership, "pk", membership)
    try:
        member = OrganizationMembership.objects.select_for_update().get(
            pk=membership_id, organization=organization,
        )
    except OrganizationMembership.DoesNotExist:
        raise ValidationError("The membership does not belong to this organization.") from None
    return organization, member


def _update_team_member(organization, member, *, role=None, status=None):
    role = member.role if role is None else role
    status = member.status if status is None else status
    active_owner = OrganizationMembership.objects.filter(
        organization=organization, role=OrganizationMembership.Role.OWNER,
        status=OrganizationMembership.Status.ACTIVE,
    ).exclude(pk=member.pk)
    was_owner = member.role == "OWNER" and member.status == "ACTIVE"
    will_be_owner = role == "OWNER" and status == "ACTIVE"
    if was_owner and not will_be_owner and not active_owner.exists():
        raise ValidationError("The sole active owner cannot be demoted, suspended, or removed.")
    if will_be_owner and active_owner.exists():
        raise ValidationError("This organization already has an active owner. Transfer ownership separately.")
    if (role, status) == (member.role, member.status):
        return member
    member.role = role
    member.status = status
    # Update only the scoped membership; never the login account or owner link.
    member.save(update_fields=["role", "status", "updated_at"])
    return member


@transaction.atomic
def change_team_member_role(*, organization, actor, membership, role):
    """Change an active/suspended member's team role; ownership transfers are separate."""
    organization, member = _locked_team_member(organization, actor, membership)
    if role not in TEAM_ROLES and role != member.role:
        raise ValidationError({"role": "Choose manager, recruiter, or viewer. Transfer ownership separately."})
    if member.status == OrganizationMembership.Status.REMOVED:
        raise ValidationError("Restore the removed membership before changing its role.")
    return _update_team_member(organization, member, role=role)


@transaction.atomic
def suspend_team_member(*, organization, actor, membership):
    """Suspend access within this organization without disabling the account."""
    organization, member = _locked_team_member(organization, actor, membership)
    if member.status == OrganizationMembership.Status.REMOVED:
        raise ValidationError("A removed membership cannot be suspended.")
    return _update_team_member(organization, member, status=OrganizationMembership.Status.SUSPENDED)


@transaction.atomic
def restore_team_member(*, organization, actor, membership):
    """Restore suspended/removed access, preserving the membership's current role."""
    organization, member = _locked_team_member(organization, actor, membership)
    return _update_team_member(organization, member, status=OrganizationMembership.Status.ACTIVE)


@transaction.atomic
def remove_team_member(*, organization, actor, membership):
    """Soft-remove a membership, preserving history and every other organization."""
    organization, member = _locked_team_member(organization, actor, membership)
    return _update_team_member(organization, member, status=OrganizationMembership.Status.REMOVED)


@transaction.atomic
def transfer_organization_ownership(*, organization, actor, membership):
    """Return the organization after transferring ownership to an active member.

    Lock order: organization, memberships by primary key, accounts by primary key.
    Demotion precedes promotion to respect the immediate single-owner constraint;
    the transaction exposes only the complete transfer to other transactions.
    """
    organization = Organization.objects.select_for_update().get(pk=organization.pk)
    require_organization_capability(
        actor, organization, OrganizationCapability.TRANSFER_OWNERSHIP,
        allow_legacy_owner=False,
    )
    membership_id = getattr(membership, "pk", membership)
    # Only fetch records within this organization, even for stale/tampered objects.
    members = list(OrganizationMembership.objects.select_for_update().filter(
        organization=organization,
    ).filter(Q(user_id=actor.pk) | Q(pk=membership_id)).order_by("pk"))
    current_owner = next((member for member in members if member.user_id == actor.pk), None)
    successor = next((member for member in members if member.pk == membership_id), None)
    if current_owner is None or current_owner.role != "OWNER" or current_owner.status != "ACTIVE":
        raise PermissionDenied("Only the current active owner can transfer ownership.")
    if successor is None:
        raise ValidationError("The successor membership does not belong to this organization.")
    if successor.pk == current_owner.pk:
        raise ValidationError("Choose a different member as the new owner.")
    if successor.status != "ACTIVE" or successor.role not in TEAM_ROLES:
        raise ValidationError("Ownership can only be transferred to an active team member.")

    # Account locks keep activation and concurrent owner-link assignments stable.
    accounts = list(get_user_model().objects.select_for_update().filter(
        pk__in=[current_owner.user_id, successor.user_id],
    ).order_by("pk"))
    active_accounts = {account.pk for account in accounts if account.is_active}
    if actor.pk not in active_accounts:
        raise PermissionDenied("An active owner account is required.")
    if successor.user_id not in active_accounts:
        raise ValidationError("The successor's account must be active.")
    # Organization.user is a OneToOneField: never steal another organization's
    # linked account or change its membership to make a transfer possible.
    if Organization.objects.filter(user_id=successor.user_id).exclude(pk=organization.pk).exists():
        raise ValidationError("The successor is already the linked owner of another organization.")

    current_owner.role = OrganizationMembership.Role.MANAGER
    current_owner.save(update_fields=["role", "updated_at"])
    successor.role = OrganizationMembership.Role.OWNER
    successor.save(update_fields=["role", "updated_at"])
    organization.user_id = successor.user_id
    organization.save(update_fields=["user"])
    return organization

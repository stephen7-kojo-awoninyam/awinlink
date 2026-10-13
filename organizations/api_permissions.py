from django.contrib.auth import get_user_model
from rest_framework.permissions import BasePermission

from .permissions import OrganizationCapability, has_organization_capability


class IsOrganizationTeamOwner(BasePermission):
    message = "Only the current organization owner can manage this team."
    capability = OrganizationCapability.MANAGE_MEMBERS
    allow_legacy_owner = True

    def has_object_permission(self, request, view, organization):
        return has_organization_capability(
            request.user, organization, self.capability,
            allow_legacy_owner=self.allow_legacy_owner,
        )


class CanTransferOrganizationOwnership(IsOrganizationTeamOwner):
    capability = OrganizationCapability.TRANSFER_OWNERSHIP
    allow_legacy_owner = False


class IsTeamInvitationRecipient(BasePermission):
    message = "Only the active invitation recipient can respond."

    def has_object_permission(self, request, view, invitation):
        return (
            invitation.recipient_id == request.user.pk
            and get_user_model().objects.filter(pk=request.user.pk, is_active=True).exists()
        )

from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from django.urls import reverse
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .api_permissions import (
    CanTransferOrganizationOwnership, IsOrganizationTeamOwner,
    IsTeamInvitationRecipient,
)
from .api_serializers import (
    OwnershipTransferSerializer, TeamInvitationResponseSerializer,
    TeamInvitationSerializer, TeamMemberRoleSerializer, TeamMemberSerializer,
    TeamInvitationCreateSerializer,
)
from .models import Organization, OrganizationMembership, OrganizationTeamInvitation


class TeamAPIView(APIView):
    def handle_exception(self, exc):
        # Existing services expose Django exceptions; translate validation into
        # DRF's 400 responses without changing the services or other endpoints.
        if isinstance(exc, DjangoValidationError):
            detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}
            exc = ValidationError(detail)
        elif isinstance(exc, ObjectDoesNotExist):
            exc = NotFound()
        return super().handle_exception(exc)


class OrganizationTeamAPIView(TeamAPIView):
    permission_classes = [IsAuthenticated, IsOrganizationTeamOwner]

    def get_organization(self, request, organization_id):
        organization = get_object_or_404(Organization, pk=organization_id)
        self.check_object_permissions(request, organization)
        return organization

    def get_member(self, organization, membership_id):
        return get_object_or_404(
            OrganizationMembership, pk=membership_id, organization=organization,
        )


class TeamMemberListAPIView(OrganizationTeamAPIView):
    def get(self, request, organization_id):
        organization = self.get_organization(request, organization_id)
        members = services.list_team_members(organization=organization, actor=request.user)
        return Response(TeamMemberSerializer(members, many=True).data)


class TeamMemberRoleAPIView(OrganizationTeamAPIView):
    def patch(self, request, organization_id, membership_id):
        organization = self.get_organization(request, organization_id)
        member = self.get_member(organization, membership_id)
        serializer = TeamMemberRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = services.change_team_member_role(
            organization=organization, actor=request.user, membership=member,
            role=serializer.validated_data["role"],
        )
        return Response(TeamMemberSerializer(updated).data)


class TeamMemberStatusAPIView(OrganizationTeamAPIView):
    def post(self, request, organization_id, membership_id):
        organization = self.get_organization(request, organization_id)
        member = self.get_member(organization, membership_id)
        updated = self.service(organization=organization, actor=request.user, membership=member)
        return Response(TeamMemberSerializer(updated).data)


class TeamMemberSuspendAPIView(TeamMemberStatusAPIView):
    service = staticmethod(services.suspend_team_member)


class TeamMemberRestoreAPIView(TeamMemberStatusAPIView):
    service = staticmethod(services.restore_team_member)


class TeamMemberRemoveAPIView(TeamMemberStatusAPIView):
    service = staticmethod(services.remove_team_member)


class OwnershipTransferAPIView(OrganizationTeamAPIView):
    permission_classes = [IsAuthenticated, CanTransferOrganizationOwnership]

    def post(self, request, organization_id):
        organization = self.get_organization(request, organization_id)
        serializer = OwnershipTransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        member = self.get_member(organization, serializer.validated_data["membership_id"])
        updated = services.transfer_organization_ownership(
            organization=organization, actor=request.user, membership=member,
        )
        return Response({"organization": updated.pk, "owner": updated.user_id})


class TeamInvitationResponseAPIView(TeamAPIView):
    permission_classes = [IsAuthenticated, IsTeamInvitationRecipient]

    def post(self, request, organization_id, invitation_id):
        invitation = get_object_or_404(
            OrganizationTeamInvitation, pk=invitation_id, organization_id=organization_id,
        )
        self.check_object_permissions(request, invitation)
        serializer = TeamInvitationResponseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = self.service(
            invitation=invitation, recipient=request.user,
            token=serializer.validated_data["token"],
        )
        return Response(TeamInvitationSerializer(updated).data)


class TeamInvitationAcceptAPIView(TeamInvitationResponseAPIView):
    service = staticmethod(services.accept_team_invitation)


class TeamInvitationDeclineAPIView(TeamInvitationResponseAPIView):
    service = staticmethod(services.decline_team_invitation)


class TeamInvitationListCreateAPIView(OrganizationTeamAPIView):
    def get(self, request, organization_id):
        organization = self.get_organization(request, organization_id)
        invitations = organization.team_invitations.select_related("recipient").order_by("-created_at", "-pk")
        data = [dict(TeamInvitationSerializer(invitation).data, recipient_username=invitation.recipient.username) for invitation in invitations]
        return Response(data, headers={"Cache-Control": "no-store"})

    def post(self, request, organization_id):
        organization = self.get_organization(request, organization_id)
        serializer = TeamInvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation, token = services.create_team_invitation(
            organization=organization, inviter=request.user,
            recipient=serializer.validated_data["recipient_username"],
            role=serializer.validated_data["role"],
            expires_at=serializer.validated_data.get("expires_at"),
        )
        return Response({
            "invitation": TeamInvitationSerializer(invitation).data,
            "token": token,
            "response_url": reverse("team_invitation_response", args=[invitation.pk]),
        }, status=201, headers={"Cache-Control": "no-store"})


class TeamInvitationRevokeAPIView(OrganizationTeamAPIView):
    def post(self, request, organization_id, invitation_id):
        organization = self.get_organization(request, organization_id)
        invitation = get_object_or_404(OrganizationTeamInvitation, pk=invitation_id, organization=organization)
        updated = services.revoke_team_invitation(invitation=invitation, actor=request.user)
        return Response(TeamInvitationSerializer(updated).data)

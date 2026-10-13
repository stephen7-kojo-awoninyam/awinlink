from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from organizations.models import Organization
from organizations.permissions import (
    OrganizationCapability,
    get_request_organization,
    has_organization_capability,
    require_organization_capability,
)
from .models import Competition
from .services import is_platform_admin


def get_owned_organization(request_or_user, capability=OrganizationCapability.MANAGE_COMPETITIONS):
    request = request_or_user if hasattr(request_or_user, "user") else None
    user = request.user if request else request_or_user
    if not getattr(user, "is_authenticated", False):
        return None
    try:
        if request:
            return get_request_organization(request, capability)
        organization = Organization.objects.filter(user=user).first()
        if organization is None:
            return None
        require_organization_capability(user, organization, capability)
        return organization
    except Organization.DoesNotExist:
        return None


def get_managed_competition(request_or_user, competition_id, capability=OrganizationCapability.MANAGE_COMPETITIONS):
    request = request_or_user if hasattr(request_or_user, "user") else None
    user = request.user if request else request_or_user
    competition = get_object_or_404(
        Competition.objects.select_related("organization", "organization__user"),
        pk=competition_id,
    )
    # Platform moderation and existing administrative controls remain available,
    # including when an organization is suspended.
    if is_platform_admin(user):
        return competition
    try:
        if request:
            get_request_organization(
                request,
                capability,
                organization=competition.organization,
            )
        else:
            require_organization_capability(
                user,
                competition.organization,
                capability,
            )
    except (Organization.DoesNotExist, PermissionDenied):
        return None
    return competition


def can_view_competition(user, competition):
    return (
        competition.status in Competition.PUBLIC_STATUSES
        or is_platform_admin(user)
        or has_organization_capability(
            user,
            competition.organization,
            OrganizationCapability.VIEW_COMPETITIONS,
        )
        or (
            getattr(user, "is_authenticated", False)
            and competition.judges.filter(coach=user).exists()
        )
    )

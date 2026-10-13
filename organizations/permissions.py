from functools import wraps
from enum import Enum
from types import MappingProxyType

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.contrib.auth import get_user_model

from .models import Organization, OrganizationMembership


def require_active_organization(organization):
    """Check current database state without changing the linked login account."""
    if organization is not None and not Organization.objects.filter(
        pk=organization.pk, status="ACTIVE",
    ).exists():
        raise PermissionDenied(
            "This organization is inactive and cannot perform organization operations."
        )
    return organization


def require_user_organization_active(user):
    return require_active_organization(getattr(user, "organization_profile", None))


def has_active_organization(user):
    return user.is_authenticated and Organization.objects.filter(
        user=user, status="ACTIVE",
    ).exists()


def organization_operation(view):
    """Reject inactive owners before dispatching an organisation web action."""
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        require_user_organization_active(request.user)
        return view(request, *args, **kwargs)

    return wrapped

class OrganizationCapability(str, Enum):
    VIEW_PROFILE = "view_profile"
    EDIT_PROFILE = "edit_profile"
    VIEW_DASHBOARD = "view_dashboard"
    VIEW_TALENTS = "view_talents"
    VIEW_OPPORTUNITIES = "view_opportunities"
    MANAGE_OPPORTUNITIES = "manage_opportunities"
    VIEW_RECRUITMENT = "view_recruitment"
    MANAGE_RECRUITMENT = "manage_recruitment"
    VIEW_EVENTS = "view_events"
    MANAGE_EVENTS = "manage_events"
    VIEW_COMPETITIONS = "view_competitions"
    MANAGE_COMPETITIONS = "manage_competitions"
    VIEW_ANALYTICS = "view_analytics"
    VIEW_ADVERTISING = "view_advertising"
    MANAGE_ADVERTISING = "manage_advertising"
    VIEW_POSTS = "view_posts"
    MANAGE_POSTS = "manage_posts"
    VIEW_MEMBERS = "view_members"
    MANAGE_MEMBERS = "manage_members"
    TRANSFER_OWNERSHIP = "transfer_ownership"


_READ_CAPABILITIES = frozenset({
    OrganizationCapability.VIEW_PROFILE,
    OrganizationCapability.VIEW_DASHBOARD,
    OrganizationCapability.VIEW_TALENTS,
    OrganizationCapability.VIEW_OPPORTUNITIES,
    OrganizationCapability.VIEW_RECRUITMENT,
    OrganizationCapability.VIEW_EVENTS,
    OrganizationCapability.VIEW_COMPETITIONS,
    OrganizationCapability.VIEW_ANALYTICS,
    OrganizationCapability.VIEW_ADVERTISING,
    OrganizationCapability.VIEW_POSTS,
    OrganizationCapability.VIEW_MEMBERS,
})
_RECRUITMENT_CAPABILITIES = frozenset({
    OrganizationCapability.MANAGE_OPPORTUNITIES,
    OrganizationCapability.MANAGE_RECRUITMENT,
})
_OPERATIONAL_CAPABILITIES = _RECRUITMENT_CAPABILITIES | frozenset({
    OrganizationCapability.EDIT_PROFILE,
    OrganizationCapability.MANAGE_EVENTS,
    OrganizationCapability.MANAGE_COMPETITIONS,
    OrganizationCapability.MANAGE_ADVERTISING,
    OrganizationCapability.MANAGE_POSTS,
})
ROLE_CAPABILITIES = MappingProxyType({
    OrganizationMembership.Role.OWNER: frozenset(OrganizationCapability),
    OrganizationMembership.Role.MANAGER: _READ_CAPABILITIES | _OPERATIONAL_CAPABILITIES,
    OrganizationMembership.Role.RECRUITER: _READ_CAPABILITIES | _RECRUITMENT_CAPABILITIES,
    OrganizationMembership.Role.VIEWER: _READ_CAPABILITIES,
})


def get_organization_role(user, organization, *, allow_legacy_owner=True):
    """Resolve current database state; any membership records disable legacy fallback.

    An explicit membership is authoritative, including a reduced role or a revoked
    status. Account roles and platform admin flags do not grant organisation access.
    No memberships, owner links, or account flags are created or modified.
    """
    user_id = getattr(user, "pk", None)
    organization_id = getattr(organization, "pk", organization)
    if not getattr(user, "is_authenticated", False) or user_id is None:
        return None
    if organization_id is None:
        return None
    if not get_user_model().objects.filter(pk=user_id, is_active=True).exists():
        return None

    try:
        current = Organization.objects.filter(pk=organization_id).values(
            "pk", "status", "user_id",
        ).first()
    except (TypeError, ValueError):
        return None
    if current is None or current["status"] != "ACTIVE":
        return None

    memberships = OrganizationMembership.objects.filter(
        organization_id=current["pk"],
    )
    membership = memberships.filter(user_id=user_id).values("role", "status").first()
    if membership is not None:
        if membership["status"] != OrganizationMembership.Status.ACTIVE:
            return None
        try:
            return OrganizationMembership.Role(membership["role"])
        except ValueError:
            return None

    if (
        allow_legacy_owner
        and current["user_id"] == user_id
        and not memberships.exists()
    ):
        return OrganizationMembership.Role.OWNER
    return None


def get_organization_capabilities(user, organization, *, allow_legacy_owner=True):
    role = get_organization_role(
        user, organization, allow_legacy_owner=allow_legacy_owner,
    )
    return ROLE_CAPABILITIES.get(role, frozenset())


def has_organization_capability(user, organization, capability, *, allow_legacy_owner=True):
    try:
        capability = OrganizationCapability(capability)
    except (ValueError, TypeError):
        return False
    return capability in get_organization_capabilities(
        user, organization, allow_legacy_owner=allow_legacy_owner,
    )


def require_organization_capability(user, organization, capability, *, allow_legacy_owner=True):
    """Raise Django/DRF-compatible PermissionDenied; return the granted effective role."""
    try:
        capability = OrganizationCapability(capability)
    except (ValueError, TypeError):
        raise PermissionDenied("Unknown organization capability.") from None
    role = get_organization_role(
        user, organization, allow_legacy_owner=allow_legacy_owner,
    )
    if capability not in ROLE_CAPABILITIES.get(role, frozenset()):
        raise PermissionDenied("You do not have access to this organization capability.")
    return role


def get_request_organization(request, capability, *, organization=None):
    """Resolve a workspace without changing existing URLs or payload fields.

    Legacy defaults remain stable. A unique membership supplies the default for a
    team member; ambiguous memberships require an organization_id query parameter.
    Object-specific callers pass the object's actual organisation.
    """
    selector = request.GET.get("organization_id")
    if selector is not None:
        try:
            selected_id = int(selector)
            if selected_id <= 0:
                raise ValueError
        except (TypeError, ValueError):
            raise PermissionDenied("Invalid organization selection.") from None
        if organization is not None and organization.pk != selected_id:
            raise PermissionDenied("The object belongs to a different organization.")
        organization = Organization.objects.get(pk=selected_id)

    if organization is None:
        organization = Organization.objects.filter(user=request.user).first()
        if organization is None:
            memberships = OrganizationMembership.objects.filter(user=request.user)
            current = memberships.filter(status="ACTIVE")
            ids = list(current.values_list("organization_id", flat=True).distinct()[:2])
            if not ids:
                ids = list(memberships.values_list("organization_id", flat=True).distinct()[:2])
            if len(ids) > 1:
                raise PermissionDenied("Select an organization using organization_id.")
            if not ids:
                raise Organization.DoesNotExist("You do not have an organization profile.")
            organization = Organization.objects.get(pk=ids[0])

    require_organization_capability(request.user, organization, capability)
    return organization


def require_request_organization(request, capability, *, organization=None):
    """Web counterpart: missing workspace access is a permission denial."""
    try:
        return get_request_organization(request, capability, organization=organization)
    except Organization.DoesNotExist:
        raise PermissionDenied("You do not have access to this organization.") from None


def organizations_for_capability(user, capability):
    """Query organisation scope using the same membership and legacy policy."""
    try:
        capability = OrganizationCapability(capability)
    except (TypeError, ValueError):
        return Organization.objects.none()
    if (
        not getattr(user, "is_authenticated", False)
        or getattr(user, "pk", None) is None
        or not get_user_model().objects.filter(pk=user.pk, is_active=True).exists()
    ):
        return Organization.objects.none()
    roles = [role for role, capabilities in ROLE_CAPABILITIES.items() if capability in capabilities]
    return Organization.objects.filter(status="ACTIVE").filter(
        Q(
            memberships__user_id=user.pk,
            memberships__status="ACTIVE",
            memberships__role__in=roles,
        )
        | Q(user_id=user.pk, memberships__isnull=True)
    ).distinct()

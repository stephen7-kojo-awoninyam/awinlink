"""Read-only presentation helpers using the existing organization policy."""
from django import template
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from organizations.models import Organization
from organizations.permissions import (
    OrganizationCapability, get_request_organization, has_organization_capability,
)

register = template.Library()


@register.simple_tag(takes_context=True)
def event_workspace(context):
    request = context.get("request")
    if request is None or not getattr(request.user, "pk", None):
        return None
    try:
        return get_request_organization(request, OrganizationCapability.VIEW_EVENTS)
    except (PermissionDenied, Organization.DoesNotExist):
        return None


@register.simple_tag
def event_access(user, organization, capability):
    if organization is None:
        return False
    return has_organization_capability(user, organization, capability)


@register.simple_tag
def event_registration_open(event, capacity_full=False):
    return (
        event.status == "PUBLISHED"
        and event.organizer.status == "ACTIVE"
        and event.registration_deadline > timezone.now()
        and not capacity_full
    )

"""Presentation helpers delegate to the existing competition permission policy."""
from django import template
from django.core.exceptions import PermissionDenied

from organizations.permissions import OrganizationCapability, has_organization_capability
from competitions.permissions import get_owned_organization
from competitions.services import is_platform_admin

register = template.Library()


@register.simple_tag(takes_context=True)
def competition_workspace(context):
    request = context.get("request")
    if request is None or not getattr(request.user, "pk", None):
        return None
    try:
        return get_owned_organization(request, OrganizationCapability.VIEW_COMPETITIONS)
    except PermissionDenied:
        return None


@register.simple_tag(takes_context=True)
def competition_access(context, user, organization, capability="manage_competitions"):
    if organization is None:
        return False
    cache = context.render_context.setdefault("competition_ui_access", {})
    key = (getattr(user, "pk", None), getattr(organization, "pk", None), capability)
    if key not in cache:
        cache[key] = has_organization_capability(user, organization, capability)
    return cache[key]


@register.simple_tag
def competition_admin(user):
    return is_platform_admin(user)

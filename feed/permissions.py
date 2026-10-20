"""Authorization for the identities and workspaces represented by a post."""
from django.core.exceptions import PermissionDenied
from organizations.permissions import OrganizationCapability, require_organization_capability


def authorize_post_associations(user, attributes, *, instance=None):
    # Recheck both old and new associations: a demoted/revoked member cannot
    # bypass permissions by detaching the old workspace in the same request.
    for source in ([instance] if instance is not None else []) + [attributes]:
        get = source.get if isinstance(source, dict) else lambda name: getattr(source, name, None)
        talent, organization, event = (get(name) for name in ('talent', 'organization', 'event'))
        if talent is not None and talent.user_id != user.pk:
            raise PermissionDenied('You cannot post on behalf of another talent.')
        if organization is not None:
            require_organization_capability(user, organization, OrganizationCapability.MANAGE_POSTS)
        if event is not None:
            require_organization_capability(user, event.organizer, OrganizationCapability.MANAGE_POSTS)
            if organization is not None and event.organizer_id != organization.pk:
                raise PermissionDenied('The event belongs to a different organization.')

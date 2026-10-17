from django.db.models import Q

from organizations.permissions import OrganizationCapability, organizations_for_capability

from .models import TalentProfile


def visible_talent_profiles_for(user):
    """Public profiles, the viewer's own profile, and active organisations' access."""
    visibility = Q(profile_visibility="PUBLIC")
    if user.is_authenticated:
        visibility |= Q(user=user)
        if organizations_for_capability(user, OrganizationCapability.VIEW_TALENTS).exists():
            visibility |= Q(profile_visibility="ORGANIZATIONS")
    from accounts.safety import blocked_user_ids
    return TalentProfile.objects.filter(visibility, user__is_active=True).exclude(user_id__in=blocked_user_ids(user))

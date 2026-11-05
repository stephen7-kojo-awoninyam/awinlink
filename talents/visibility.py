from django.db.models import Q

from organizations.permissions import OrganizationCapability, organizations_for_capability

from .models import TalentProfile


def visible_talent_profiles_for(user):
    """Public profiles, the viewer's own profile, and active organisations' access."""
    from accounts.models import User
    if user is None:
        from django.contrib.auth.models import AnonymousUser
        user = AnonymousUser()
    if user.is_authenticated and not User.objects.filter(pk=user.pk, is_active=True).exists():
        return TalentProfile.objects.none()
    visibility = Q(profile_visibility="PUBLIC")
    if user.is_authenticated:
        visibility |= Q(user=user)
        if organizations_for_capability(user, OrganizationCapability.VIEW_TALENTS).exists():
            visibility |= Q(profile_visibility="ORGANIZATIONS")
    from accounts.safety import blocked_user_ids
    from accounts.age_safety import visible_users_for, approved_authorizations
    if user.is_authenticated:
        visibility |= Q(user_id__in=approved_authorizations().filter(guardian_id=user.pk).values("child_id"))
    return TalentProfile.objects.filter(visibility, user__in=visible_users_for(user)).exclude(user_id__in=blocked_user_ids(user))


def public_talent_profiles_for(user):
    """Recruiter workflows retain their public-only restriction, including blocks."""
    return visible_talent_profiles_for(user).filter(profile_visibility='PUBLIC')

from django.db.models import Q

from accounts.models import User
from accounts.safety import blocked_user_ids
from talents.models import TalentProfile
from talents.visibility import visible_talent_profiles_for
from .models import AthleteProfile


def visible_athlete_profiles_for(user):
    """Legacy-only profiles are owner-only; linked profiles share the talent ACL."""
    if user.is_authenticated and not User.objects.filter(pk=user.pk, is_active=True).exists():
        return AthleteProfile.objects.none()
    scope = Q(user_id__in=visible_talent_profiles_for(user).values('user_id'))
    if user.is_authenticated:
        scope |= Q(user_id=user.pk) & ~Q(user_id__in=TalentProfile.objects.values('user_id'))
    return AthleteProfile.objects.filter(scope, user__is_active=True).exclude(
        user_id__in=blocked_user_ids(user))

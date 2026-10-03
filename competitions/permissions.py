from django.shortcuts import get_object_or_404

from organizations.models import Organization

from .models import Competition
from .services import is_platform_admin


def get_owned_organization(user):
    if not user.is_authenticated or user.role != "ORGANIZATION":
        return None
    return Organization.objects.filter(user=user).first()


def get_managed_competition(user, competition_id):
    competition = get_object_or_404(
        Competition.objects.select_related("organization", "organization__user"),
        pk=competition_id,
    )
    if (
        is_platform_admin(user)
        or (
            user.is_authenticated
            and competition.organization.user_id == user.pk
        )
    ):
        return competition
    return None


def can_view_competition(user, competition):
    return (
        competition.status in Competition.PUBLIC_STATUSES
        or is_platform_admin(user)
        or (
            user.is_authenticated
            and competition.organization.user_id == user.pk
        )
        or (
            user.is_authenticated
            and competition.judges.filter(coach=user).exists()
        )
    )

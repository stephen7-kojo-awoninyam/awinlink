"""Shared portfolio authorization for pages, APIs and media delivery."""
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from accounts.models import User
from talents.models import TalentProfile
from talents.visibility import visible_talent_profiles_for
from .models import PortfolioItem


OWNERSHIP_FIELDS = frozenset({'talent', 'talent_id', 'user', 'user_id', 'owner', 'owner_id'})


def visible_portfolio_items_for(user):
    if getattr(user, 'is_authenticated', False) and not User.objects.filter(pk=user.pk, is_active=True).exists():
        return PortfolioItem.objects.none()
    return PortfolioItem.objects.filter(talent__in=visible_talent_profiles_for(user)).select_related('talent__user')


def visible_portfolio_talent_for(user, talent_id):
    if getattr(user, 'is_authenticated', False) and not User.objects.filter(pk=user.pk, is_active=True).exists():
        raise PermissionDenied('This account is unavailable.')
    return get_object_or_404(visible_talent_profiles_for(user), pk=talent_id)


def owned_portfolio_talent_for(user):
    if not getattr(user, 'is_authenticated', False) or not User.objects.filter(
        pk=user.pk, is_active=True, role='ATHLETE',
    ).exists():
        raise PermissionDenied('Only active talent accounts can manage their portfolio.')
    return get_object_or_404(TalentProfile, user_id=user.pk)


def owned_portfolio_item_for(user, item_id):
    talent = owned_portfolio_talent_for(user)
    return get_object_or_404(PortfolioItem.objects.select_related('talent__user'), pk=item_id, talent=talent)

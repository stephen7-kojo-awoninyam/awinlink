from django.db.models import Q
from django.core.exceptions import PermissionDenied
from .models import UserBlock


def blocked_user_ids(user):
    if not user or not user.is_authenticated:
        return set()
    pairs = UserBlock.objects.filter(Q(user=user) | Q(blocked_user=user)).values_list('user_id', 'blocked_user_id')
    return {pk for pair in pairs for pk in pair if pk != user.pk}


def require_unblocked(user, other_ids):
    if blocked_user_ids(user).intersection(other_ids):
        raise PermissionDenied('This interaction is unavailable because an account is blocked.')

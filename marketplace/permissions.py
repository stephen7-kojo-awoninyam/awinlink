from django.contrib.auth import get_user_model
from rest_framework.exceptions import PermissionDenied
from accounts.models import UserBlock
from django.db.models import Q
from organizations.permissions import has_organization_capability
from scouts.models import ScoutProfile
from coaches.models import CoachProfile


def active(user):
    return get_user_model().objects.filter(pk=user.pk, is_active=True).exists()


def blocked(a, b):
    return UserBlock.objects.filter(Q(user_id=a, blocked_user_id=b) | Q(user_id=b, blocked_user_id=a)).exists()


def can_offer(user, organization=None):
    if not active(user):
        return False
    if organization:
        return has_organization_capability(user, organization, "manage_recruitment")
    return ((user.role == "SCOUT" and ScoutProfile.objects.filter(user=user, verified=True).exists())
            or (user.role == "COACH" and CoachProfile.objects.filter(user=user, verified=True).exists()))


def require_participant(user, offer):
    if not active(user) or blocked(offer.sender_id, offer.listing.talent.user_id):
        raise PermissionDenied("Deal room unavailable.")
    if user.pk == offer.listing.talent.user_id:
        return
    if user.pk == offer.sender_id and can_offer(user, offer.organization):
        return
    raise PermissionDenied("Only the talent and authorized sender can access this deal room.")

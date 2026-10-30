"""Verification evidence is restricted to its owner and current platform reviewers."""
from accounts.models import User
from django.db.models import Q


def verification_reviewer(user):
    return bool(getattr(user, 'is_authenticated', False) and User.objects.filter(
        pk=user.pk, is_active=True,
    ).filter(Q(is_superuser=True) | Q(role='ADMIN')).exists())


def can_read_verification_document(user, names):
    from .models import VerificationRequest
    if not getattr(user, 'is_authenticated', False) or not User.objects.filter(
        pk=user.pk, is_active=True,
    ).exists():
        return False
    requests = VerificationRequest.objects.filter(document__in=names)
    if verification_reviewer(user):
        return requests.exists()
    return requests.filter(talent__user_id=user.pk).exists()

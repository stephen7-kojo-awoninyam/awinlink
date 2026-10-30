"""Roles and authority fields accepted by public account flows.

Administrator provisioning remains a trusted server-side operation. These rules
do not rewrite existing users or change the authority of legitimate admins.
"""
from django.core.exceptions import ValidationError


PUBLIC_ROLE_CHOICES = (
    ('ATHLETE', 'Athlete'),
    ('ORGANIZATION', 'Organization'),
    ('SCOUT', 'Scout'),
    ('COACH', 'Coach'),
)
PUBLIC_ROLES = frozenset(role for role, _ in PUBLIC_ROLE_CHOICES)
AUTHORITY_FIELDS = frozenset({'is_staff', 'is_superuser', 'is_active', 'groups', 'user_permissions'})


def validate_public_authority_input(data):
    if AUTHORITY_FIELDS.intersection(data):
        raise ValidationError('Account permissions cannot be set through this form.')


def active_user_has_role(user, role):
    from .models import User
    return bool(getattr(user, 'is_authenticated', False) and User.objects.filter(
        pk=user.pk, role=role, is_active=True,
    ).exists())

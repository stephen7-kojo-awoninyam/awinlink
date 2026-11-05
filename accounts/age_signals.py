"""Allow account deletion while failing closed for affected child authorizations."""
from django.db import transaction
from django.db.models import Q
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils import timezone

from .models import GuardianAuthorization, GuardianAuditEvent, User


@receiver(pre_delete, sender=User)
def restrict_children_before_guardian_or_reviewer_deletion(sender, instance, using, **kwargs):
    from .age_policy import _locked
    ids = list(GuardianAuthorization.objects.using(using).filter(
        Q(guardian_id=instance.pk) | Q(verified_by_id=instance.pk)
    ).exclude(status="REVOKED").values_list("pk", flat=True))
    with transaction.atomic(using=using):
        for authorization_id in sorted(ids):
            authorization, child = _locked(authorization_id)
            authorization.status = "REVOKED"
            authorization.revoked_at = timezone.now()
            authorization.save(update_fields=["status", "revoked_at"], using=using)
            if child.age_group != "ADULT":
                child.is_active = False
                child.save(update_fields=["is_active"], using=using)
                from .guardian_permissions import restrict_live_access
                restrict_live_access(child.pk)
            GuardianAuditEvent.objects.using(using).create(authorization=authorization, action="AUTHORIZER_DELETED")

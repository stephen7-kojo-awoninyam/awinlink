"""A visibility withdrawal also withdraws Rising Talent discovery consent."""
from django.db.models.signals import post_save
from django.dispatch import receiver
from talents.models import TalentProfile


@receiver(post_save, sender=TalentProfile)
def withdraw_private_profile(sender, instance, **kwargs):
    if instance.profile_visibility == "PUBLIC":
        return
    from .models import RisingTalentPreference
    from .rising_talent import purge_talent
    if RisingTalentPreference.objects.filter(user_id=instance.user_id, discovery_enabled=True).update(discovery_enabled=False):
        purge_talent(instance.pk)

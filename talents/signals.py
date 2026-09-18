from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import VerificationRequest



@receiver(post_save, sender=VerificationRequest)
def update_talent_verification(sender, instance, **kwargs):


    if instance.status == "APPROVED":


        talent = instance.talent


        if not talent.verified:

            talent.verified = True

            talent.save()
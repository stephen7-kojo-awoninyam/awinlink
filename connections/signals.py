from django.db.models import Case, F, IntegerField, Value, When
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from connections.models import Follow
from talents.models import TalentProfile


@receiver(post_save, sender=Follow)
def increment_cached_talent_followers(sender, instance, created, **kwargs):
    if created:
        TalentProfile.objects.filter(user_id=instance.following_id).update(
            followers_count=F("followers_count") + 1,
        )


@receiver(post_delete, sender=Follow)
def decrement_cached_talent_followers(sender, instance, **kwargs):
    TalentProfile.objects.filter(user_id=instance.following_id).update(
        followers_count=Case(
            When(followers_count__gt=0, then=F("followers_count") - 1),
            default=Value(0),
            output_field=IntegerField(),
        ),
    )

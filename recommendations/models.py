from django.db import models
from django.conf import settings
from athletes.models import AthleteProfile
from clubs.models import Club
# Create your models here.

class Recommendation(models.Model):

    athlete = models.ForeignKey(
        AthleteProfile,
        on_delete=models.CASCADE
    )

    club = models.ForeignKey(
        Club,
        on_delete=models.CASCADE
    )

    score = models.DecimalField(
        max_digits=5,
        decimal_places=2
    )

    reason = models.TextField()

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["-score"]

    def __str__(self):
        return f"{self.club.name} → {self.athlete.user.username}"


class RecommendationInterestPreference(models.Model):
    """Per-user consent for using activity to infer recommendation topics."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="recommendation_interest_preference",
    )
    inferred_interests_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Interest inference preference for user {self.user_id}"


class RecommendationFeedback(models.Model):
    """Deduplicated per-user impressions and dismissals for recommendation items."""

    class ItemKind(models.TextChoices):
        FEED = "FEED", "Feed"
        TALENT = "TALENT", "Talent"
        CONNECTION = "CONNECTION", "Connection"
        OPPORTUNITY = "OPPORTUNITY", "Opportunity"
        LEARNING = "LEARNING", "Learning"
        EVENT = "EVENT", "Event"

    class Action(models.TextChoices):
        IMPRESSION = "IMPRESSION", "Impression"
        DISMISSED = "DISMISSED", "Dismissed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="recommendation_feedback",
    )
    item_kind = models.CharField(max_length=16, choices=ItemKind.choices)
    item_id = models.PositiveBigIntegerField()
    action = models.CharField(max_length=12, choices=Action.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "item_kind", "item_id", "action"),
                name="recommendation_feedback_once_per_action",
            ),
            models.CheckConstraint(
                condition=models.Q(item_id__gt=0),
                name="recommendation_feedback_positive_item_id",
            ),
        ]
        indexes = [
            models.Index(fields=("user", "action", "item_kind"), name="rec_feedback_user_action_idx"),
        ]

    def __str__(self):
        return f"{self.user_id} {self.action.lower()} {self.item_kind.lower()} {self.item_id}"

from django.db import models

from talents.models import TalentProfile

# create your models here.

class TalentScore(models.Model):

    talent = models.OneToOneField(
        TalentProfile,
        on_delete=models.CASCADE,
        related_name="talent_score"
    )

    physical_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0
    )

    performance_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0
    )

    achievement_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0
    )

    experience_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0
    )

    verification_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0
    )

    overall_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return f"{self.talent.user.username} - {self.overall_score}"

# =========================================================
# TALENT PROFILE VIEW
# =========================================================

class TalentProfileView(models.Model):

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="profile_views"
    )

    talent = models.ForeignKey(
        "talents.TalentProfile",
        on_delete=models.CASCADE,
        related_name="profile_views"
    )

    viewed_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):

        return (
            f"{self.organization.name} viewed "
            f"{self.talent.user.get_full_name()}"
        )


# =========================================================
# RECOMMENDATION HISTORY
# =========================================================

class RecommendationHistory(models.Model):

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="recommendation_history"
    )

    talent = models.ForeignKey(
        "talents.TalentProfile",
        on_delete=models.CASCADE,
        related_name="recommendation_history"
    )

    opportunity = models.ForeignKey(
        "opportunities.Opportunity",
        on_delete=models.CASCADE,
        related_name="recommendation_history"
    )

    score = models.FloatField()

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:

        ordering = [
            "-created_at"
        ]

    def __str__(self):

        return (
            f"{self.organization.name} → "
            f"{self.talent.user.get_full_name()} "
            f"({self.score}%)"
        )
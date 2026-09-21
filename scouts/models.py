from django.db import models
from django.conf import settings

from talents.models import TalentProfile

# Create your models here.




# =========================================================
# SCOUT PROFILE
# =========================================================

class ScoutProfile(models.Model):

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="scout_profile"
    )
    
    SCOUT_CATEGORY_CHOICES = (
        ("SPORTS", "Sports"),
        ("SCIENCE_TECHNOLOGY", "Science & Technology"),
        ("ARTS", "Arts"),
        ("OTHERS", "Others"),
    )

    scout_category = models.CharField(
        max_length=30,
        choices=SCOUT_CATEGORY_CHOICES,
        blank=True,
        null=True
    )

    headline = models.CharField(
        max_length=255,
        blank=True
    )

    biography = models.TextField(
        blank=True
    )

    specialization = models.CharField(
        max_length=255,
        blank=True
    )

    country = models.CharField(
        max_length=100,
        blank=True
    )

    city = models.CharField(
        max_length=100,
        blank=True
    )

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scouts"
    )

    verified = models.BooleanField(
        default=False
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):

        return (
            self.user.get_full_name()
            or self.user.username
        )


# =========================================================
# SCOUT TALENT VIEW
# =========================================================

class ScoutTalentView(models.Model):

    scout = models.ForeignKey(
        ScoutProfile,
        on_delete=models.CASCADE,
        related_name="talent_views"
    )

    talent = models.ForeignKey(
        TalentProfile,
        on_delete=models.CASCADE,
        related_name="scout_views"
    )

    viewed_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):

        return (
            f"{self.scout.user.username} viewed "
            f"{self.talent.user.username}"
        )


# =========================================================
# SCOUT TALENT FOLLOW
# =========================================================

class ScoutTalentFollow(models.Model):

    scout = models.ForeignKey(
        ScoutProfile,
        on_delete=models.CASCADE,
        related_name="followed_talents"
    )

    talent = models.ForeignKey(
        TalentProfile,
        on_delete=models.CASCADE,
        related_name="scout_followers"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:

        unique_together = (
            "scout",
            "talent",
        )

    def __str__(self):

        return (
            f"{self.scout.user.username} follows "
            f"{self.talent.user.username}"
        )


# =========================================================
# SCOUT TALENT BOOKMARK
# =========================================================

class ScoutTalentBookmark(models.Model):

    scout = models.ForeignKey(
        ScoutProfile,
        on_delete=models.CASCADE,
        related_name="saved_talents"
    )

    talent = models.ForeignKey(
        TalentProfile,
        on_delete=models.CASCADE,
        related_name="scout_bookmarks"
    )

    notes = models.TextField(
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:

        unique_together = (
            "scout",
            "talent",
        )

    def __str__(self):

        return (
            f"{self.scout.user.username} bookmarked "
            f"{self.talent.user.username}"
        )
from django.db import models

from config import settings

# Create your models here.

class CoachProfile(models.Model):

    EXPERIENCE_LEVELS = (
        ("BEGINNER", "Beginner"),
        ("INTERMEDIATE", "Intermediate"),
        ("PROFESSIONAL", "Professional"),
        ("EXPERT", "Expert"),
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="coach_profile"
    )

    headline = models.CharField(
        max_length=200,
        blank=True
    )

    biography = models.TextField(
        blank=True
    )

    specialization = models.CharField(
        max_length=200,
        blank=True
    )

    experience_level = models.CharField(
        max_length=30,
        choices=EXPERIENCE_LEVELS,
        default="BEGINNER"
    )

    years_of_experience = models.PositiveIntegerField(
        default=0
    )

    sport = models.ForeignKey(
        "sports.Sport",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coaches"
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
        related_name="coaches"
    )

    profile_photo = models.ImageField(
        upload_to="coaches/profiles/",
        blank=True,
        null=True
    )

    cover_photo = models.ImageField(
        upload_to="coaches/covers/",
        blank=True,
        null=True
    )

    certifications = models.TextField(
        blank=True,
        help_text="Coaching certifications and qualifications."
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

    class Meta:
        ordering = [
            "-created_at"
        ]

    def __str__(self):
        return (
            f"{self.user.get_full_name() or self.user.username}"
            " - Coach"
        )
        

# =========================================================
# COACH TALENT PROFILE VIEW
# =========================================================

class CoachTalentView(models.Model):

    coach = models.ForeignKey(
        CoachProfile,
        on_delete=models.CASCADE,
        related_name="talent_views"
    )

    talent = models.ForeignKey(
        "talents.TalentProfile",
        on_delete=models.CASCADE,
        related_name="coach_views"
    )

    viewed_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = [
            "-viewed_at"
        ]

    def __str__(self):

        return (
            f"{self.coach.user.username} viewed "
            f"{self.talent.user.get_full_name()}"
        )


# =========================================================
# COACH TALENT TRACKING
# =========================================================

class CoachTalentFollow(models.Model):

    coach = models.ForeignKey(
        CoachProfile,
        on_delete=models.CASCADE,
        related_name="followed_talents"
    )

    talent = models.ForeignKey(
        "talents.TalentProfile",
        on_delete=models.CASCADE,
        related_name="coached_by"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:

        constraints = [

            models.UniqueConstraint(
                fields=[
                    "coach",
                    "talent"
                ],
                name="unique_coach_talent_follow"
            )

        ]

        ordering = [
            "-created_at"
        ]

    def __str__(self):

        return (
            f"{self.coach.user.username} follows "
            f"{self.talent.user.get_full_name()}"
        )



# =========================================================
# COACH TALENT BOOKMARK
# =========================================================

class CoachTalentBookmark(models.Model):

    coach = models.ForeignKey(
        CoachProfile,
        on_delete=models.CASCADE,
        related_name="saved_talents"
    )

    talent = models.ForeignKey(
        "talents.TalentProfile",
        on_delete=models.CASCADE,
        related_name="saved_by_coaches"
    )

    notes = models.TextField(
        blank=True,
        help_text="Private notes about this talent."
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:

        constraints = [

            models.UniqueConstraint(
                fields=[
                    "coach",
                    "talent"
                ],
                name="unique_coach_talent_bookmark"
            )

        ]

        ordering = [
            "-created_at"
        ]

    def __str__(self):

        return (
            f"{self.coach.user.username} saved "
            f"{self.talent.user.get_full_name()}"
        )

        
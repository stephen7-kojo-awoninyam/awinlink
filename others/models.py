from django.db import models

# Create your models here.

from django.db import models


class OtherTalentProfile(models.Model):

    talent = models.OneToOneField(
        "talents.TalentProfile",
        on_delete=models.CASCADE,
        related_name="other_profile"
    )

    # =====================================================
    # TALENT / SPECIALIZATION
    # =====================================================

    specialization = models.CharField(
        max_length=200,
        blank=True
    )

    # =====================================================
    # ABOUT THE TALENT
    # =====================================================

    description = models.TextField(
        blank=True
    )

    # =====================================================
    # FIELD / AREA
    # =====================================================

    field = models.CharField(
        max_length=200,
        blank=True
    )

    # =====================================================
    # EXPERIENCE
    # =====================================================

    experience_description = models.TextField(
        blank=True
    )

    years_of_experience = models.PositiveIntegerField(
        default=0
    )

    # =====================================================
    # SKILLS
    # =====================================================

    skills_description = models.TextField(
        blank=True
    )

    # =====================================================
    # PROJECTS / WORK
    # =====================================================

    projects_description = models.TextField(
        blank=True
    )

    # =====================================================
    # ACHIEVEMENTS
    # =====================================================

    achievements_description = models.TextField(
        blank=True
    )

    # =====================================================
    # INTERESTS
    # =====================================================

    interests = models.TextField(
        blank=True
    )

    # =====================================================
    # ONLINE PRESENCE
    # =====================================================

    website = models.URLField(
        blank=True
    )

    linkedin = models.URLField(
        blank=True
    )

    other_link = models.URLField(
        blank=True
    )

    # =====================================================
    # TIMESTAMPS
    # =====================================================

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):

        return (
            f"{self.talent.user.username} - Other Talent"
        )


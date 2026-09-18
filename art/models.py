from django.db import models

# Create your models here.

from django.db import models


class ArtsTalentProfile(models.Model):

    talent = models.OneToOneField(
        "talents.TalentProfile",
        on_delete=models.CASCADE,
        related_name="arts_profile"
    )

    # =====================================================
    # ARTS SPECIALIZATION
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
    # ARTISTIC DISCIPLINE
    # =====================================================

    discipline = models.CharField(
        max_length=200,
        blank=True
    )

    # =====================================================
    # EXPERIENCE & BACKGROUND
    # =====================================================

    experience_description = models.TextField(
        blank=True
    )

    years_of_experience = models.PositiveIntegerField(
        default=0
    )

    # =====================================================
    # SKILLS & EXPERTISE
    # =====================================================

    skills_description = models.TextField(
        blank=True
    )

    # =====================================================
    # PORTFOLIO / CREATIVE WORK
    # =====================================================

    portfolio_description = models.TextField(
        blank=True
    )

    # =====================================================
    # ACHIEVEMENTS
    # =====================================================

    achievements_description = models.TextField(
        blank=True
    )

    # =====================================================
    # CREATIVE INTERESTS
    # =====================================================

    creative_interests = models.TextField(
        blank=True
    )

    # =====================================================
    # ONLINE PRESENCE
    # =====================================================

    website = models.URLField(
        blank=True
    )

    portfolio_url = models.URLField(
        blank=True
    )

    instagram = models.URLField(
        blank=True
    )

    youtube = models.URLField(
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
            f"{self.talent.user.username} - Arts"
        )


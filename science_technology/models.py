from django.db import models

# Create your models here.



from django.db import models
from django.conf import settings


class ScienceTechnologyTalentProfile(models.Model):

    talent = models.OneToOneField(
        "talents.TalentProfile",
        on_delete=models.CASCADE,
        related_name="science_technology_profile"
    )

    specialization = models.CharField(
        max_length=200,
        blank=True
    )

    description = models.TextField(
        blank=True
    )

    education = models.TextField(
        blank=True
    )

    institution = models.CharField(
        max_length=200,
        blank=True
    )

    skills_description = models.TextField(
        blank=True
    )

    projects_description = models.TextField(
        blank=True
    )

    research_interests = models.TextField(
        blank=True
    )

    years_of_experience = models.PositiveIntegerField(
        default=0
    )

    website = models.URLField(
        blank=True
    )

    linkedin = models.URLField(
        blank=True
    )

    github = models.URLField(
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return f"{self.talent.user.username} - Science & Technology"
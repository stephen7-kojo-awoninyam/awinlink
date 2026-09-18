from django.db import models

# Create your models here.


class Shortlist(models.Model):

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="shortlisted_talents"
    )

    talent = models.ForeignKey(
        "talents.TalentProfile",
        on_delete=models.CASCADE,
        related_name="shortlisted_by"
    )

    notes = models.TextField(
        blank=True,
        help_text="Private notes about this talent."
    )

    starred = models.BooleanField(
        default=False
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:

        unique_together = (
            "organization",
            "talent",
        )

        ordering = [
            "-created_at"
        ]

    def __str__(self):

        return (
            f"{self.organization.name} - "
            f"{self.talent.user.get_full_name()}"
        )
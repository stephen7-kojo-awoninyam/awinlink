from django.db import models
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
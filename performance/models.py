
from django.db import models
from django.conf import settings
from sports.models import PerformanceMetric

# Create your models here.


class AthletePerformance(models.Model):

    athlete = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )


    metric = models.ForeignKey(
        PerformanceMetric,
        on_delete=models.CASCADE
    )


    value = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )


    recorded_date = models.DateField(
        auto_now_add=True
    )


    def __str__(self):
        return f"{self.athlete.username} - {self.metric.name}"

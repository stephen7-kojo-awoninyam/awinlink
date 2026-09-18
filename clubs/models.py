from django.db import models
from django.conf import settings
# Create your models here.



class Club(models.Model):

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="club_profile"
    )

    name = models.CharField(
        max_length=200
    )

    country = models.CharField(
        max_length=100
    )

    description = models.TextField(
        blank=True
    )

    logo = models.ImageField(
        upload_to="clubs/logos/",
        blank=True,
        null=True
    )

    verified = models.BooleanField(
        default=False
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )


    def __str__(self):
        return self.name
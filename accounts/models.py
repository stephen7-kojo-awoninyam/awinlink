from django.db import models
from django.contrib.auth.models import AbstractUser
# Create your models here.


from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):

    ROLE_CHOICES = (
        ("ATHLETE", "Athlete"),
        ("ORGANIZATION", "Organization"),
        ("SCOUT", "Scout"),
        ("COACH", "Coach"),
        ("ADMIN", "Admin"),
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default="ATHLETE"
    )

    profile_picture = models.ImageField(
        upload_to="profiles/",
        blank=True,
        null=True
    )

    phone_number = models.CharField(
        max_length=20,
        blank=True,
        null=True
    )

    country = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"{self.username} - {self.role}"
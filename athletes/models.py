from django.conf import settings
from django.db import models

# Create your models here.


class AthleteProfile(models.Model):

    EXPERIENCE_LEVELS = (
        ("BEGINNER", "Beginner"),
        ("AMATEUR", "Amateur"),
        ("PROFESSIONAL", "Professional"),
        ("ELITE", "Elite"),
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="athlete_profile"
    )

    sport = models.ForeignKey(
        "sports.Sport",
        on_delete=models.SET_NULL,
        null=True
    )

    category = models.ForeignKey(
        "sports.SportCategory",
        on_delete=models.SET_NULL,
        null=True
    )

    date_of_birth = models.DateField()

    nationality = models.CharField(
        max_length=100,
        blank=True
    )

    height = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Height in centimeters"
    )

    weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Weight in kilograms"
    )

    experience_level = models.CharField(
        max_length=20,
        choices=EXPERIENCE_LEVELS,
        default="AMATEUR"
    )

    biography = models.TextField(
        blank=True
    )

    current_team = models.CharField(
        max_length=200,
        blank=True
    )

    profile_photo = models.ImageField(
        upload_to="athletes/profile/",
        blank=True,
        null=True
    )

    cover_photo = models.ImageField(
        upload_to="athletes/cover/",
        blank=True,
        null=True
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
        return self.user.username
    
    
    
class Achievement(models.Model):

    athlete = models.ForeignKey(
        AthleteProfile,
        on_delete=models.CASCADE,
        related_name="achievements"
    )

    title = models.CharField(
        max_length=200
    )

    description = models.TextField(
        blank=True
    )

    year = models.IntegerField()


    def __str__(self):
        return self.title
    
    


class AthleteMedia(models.Model):

    MEDIA_TYPES = (
        ("VIDEO", "Video"),
        ("IMAGE", "Image"),
    )

    athlete = models.ForeignKey(
        AthleteProfile,
        on_delete=models.CASCADE,
        related_name="media"
    )

    media_type = models.CharField(
        max_length=10,
        choices=MEDIA_TYPES
    )

    file = models.FileField(
        upload_to="athletes/media/"
    )

    title = models.CharField(
        max_length=200
    )


    uploaded_at = models.DateTimeField(
        auto_now_add=True
    )


    def __str__(self):
        return self.title   
    
    

class AthleteMedia(models.Model):

    MEDIA_TYPES = (
        ("IMAGE", "Image"),
        ("VIDEO", "Video"),
    )

    athlete = models.ForeignKey(
        AthleteProfile,
        on_delete=models.CASCADE,
        related_name="media"
    )

    title = models.CharField(
        max_length=200
    )

    media_type = models.CharField(
        max_length=10,
        choices=MEDIA_TYPES
    )

    file = models.FileField(
        upload_to="athletes/media/"
    )

    description = models.TextField(
        blank=True
    )

    uploaded_at = models.DateTimeField(
        auto_now_add=True
    )


    def __str__(self):
        return self.title     
from django.db import models
# Create your models here.




class Sport(models.Model):

    name = models.CharField(
        max_length=100,
        unique=True
    )

    description = models.TextField(
        blank=True
    )

    icon = models.ImageField(
        upload_to="sports/icons/",
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )


    def __str__(self):
        return self.name
    
    
    
class SportCategory(models.Model):

    sport = models.ForeignKey(
        Sport,
        on_delete=models.CASCADE,
        related_name="categories"
    )

    name = models.CharField(
        max_length=100
    )


    description = models.TextField(
        blank=True
    )


    def __str__(self):
        return f"{self.sport.name} - {self.name}"
    
    
class PerformanceMetric(models.Model):

    sport = models.ForeignKey(
        Sport,
        on_delete=models.CASCADE,
        related_name="metrics"
    )

    name = models.CharField(
        max_length=100
    )

    unit = models.CharField(
        max_length=50
    )


    description = models.TextField(
        blank=True
    )


    def __str__(self):
        return f"{self.sport.name} - {self.name}"
    
    
class SportsTalentProfile(models.Model):

    talent = models.OneToOneField(
        "talents.TalentProfile",
        on_delete=models.CASCADE,
        related_name="sports_profile"
    )

    sport = models.ForeignKey(
        Sport,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="talent_profiles"
    )

    sport_category = models.ForeignKey(
        SportCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="talent_profiles"
    )

    position = models.CharField(
        max_length=100,
        blank=True
    )

    height = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )

    weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )

    bio = models.TextField(
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return f"{self.talent.user.username} - {self.sport}"    
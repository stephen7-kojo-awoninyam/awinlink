from django.db import models
from django.conf import settings


# =====================================
# ORGANIZATION CATEGORY
# =====================================

class OrganizationCategory(models.Model):

    name = models.CharField(
        max_length=100,
        unique=True
    )

    description = models.TextField(
        blank=True
    )

    def __str__(self):
        return self.name



# =====================================
# ORGANIZATION DOMAIN
# =====================================

class OrganizationDomain(models.Model):

    category = models.ForeignKey(
        OrganizationCategory,
        on_delete=models.CASCADE,
        related_name="domains"
    )

    name = models.CharField(
        max_length=100
    )

    description = models.TextField(
        blank=True
    )

    class Meta:

        unique_together = (
            "category",
            "name",
        )

        ordering = [
            "category",
            "name"
        ]


    def __str__(self):
        return f"{self.category.name} • {self.name}"



# =====================================
# ORGANIZATION
# =====================================

class Organization(models.Model):


    SIZE_CHOICES = (
        ("SMALL", "1-50 Employees"),
        ("MEDIUM", "51-250 Employees"),
        ("LARGE", "251-1000 Employees"),
        ("ENTERPRISE", "1000+ Employees"),
    )


    STATUS_CHOICES = (
        ("ACTIVE", "Active"),
        ("INACTIVE", "Inactive"),
        ("MERGED", "Merged"),
        ("CLOSED", "Closed"),
    )


    LEVEL_CHOICES = (
        ("GLOBAL", "Global"),
        ("CONTINENTAL", "Continental"),
        ("NATIONAL", "National"),
        ("REGIONAL", "Regional"),
        ("LOCAL", "Local"),
    )


    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="organization_profile",
        null=True,
        blank=True
    )


    name = models.CharField(
        max_length=200
    )


    category = models.ForeignKey(
        OrganizationCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="organizations"
    )


    domain = models.ForeignKey(
        OrganizationDomain,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="organizations"
    )
    
    
    cover_photo = models.ImageField(
        upload_to="organizations/covers/",
        blank=True,
        null=True
    )


    country = models.CharField(
        max_length=100
    )


    city = models.CharField(
        max_length=100,
        blank=True
    )


    headquarters = models.CharField(
        max_length=200,
        blank=True
    )


    website = models.URLField(
        blank=True
    )


    email = models.EmailField(
        blank=True
    )


    phone = models.CharField(
        max_length=30,
        blank=True
    )


    description = models.TextField(
        blank=True
    )


    logo = models.ImageField(
        upload_to="organizations/logos/",
        blank=True,
        null=True
    )


    founded_year = models.PositiveIntegerField(
        null=True,
        blank=True
    )


    organization_size = models.CharField(
        max_length=20,
        choices=SIZE_CHOICES,
        blank=True
    )


    level = models.CharField(
        max_length=20,
        choices=LEVEL_CHOICES,
        default="LOCAL"
    )


    official = models.BooleanField(
        default=True,
        help_text="Official organization seeded or verified by Awinlink."
    )


    claimed = models.BooleanField(
        default=False
    )
    
    followers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="followed_organizations"
    )

    claimed_at = models.DateTimeField(
        null=True,
        blank=True
    )


    verified = models.BooleanField(
        default=False
    )


    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="ACTIVE"
    )


    created_at = models.DateTimeField(
        auto_now_add=True
    )


    class Meta:
        ordering = [
            "name"
        ]


    def __str__(self):
        return self.name



# =====================================
# SPORTS ORGANIZATION PROFILE
# =====================================

class SportsOrganizationProfile(models.Model):


    SPORT_LEVELS = (
        ("PROFESSIONAL", "Professional"),
        ("SEMI_PRO", "Semi Professional"),
        ("AMATEUR", "Amateur"),
        ("ACADEMY", "Academy"),
        ("SCHOOL", "School"),
        ("NATIONAL_TEAM", "National Team"),
        ("FEDERATION", "Federation"),
        ("LEAGUE", "League"),
    )


    organization = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        related_name="sports_profile"
    )


    sport = models.ForeignKey(
        "sports.Sport",
        on_delete=models.CASCADE
    )


    league = models.CharField(
        max_length=200,
        blank=True
    )


    level = models.CharField(
        max_length=30,
        choices=SPORT_LEVELS,
        default="AMATEUR"
    )


    founded = models.PositiveIntegerField(
        null=True,
        blank=True
    )


    stadium = models.CharField(
        max_length=200,
        blank=True
    )


    nickname = models.CharField(
        max_length=100,
        blank=True
    )


    colors = models.CharField(
        max_length=150,
        blank=True
    )


    website = models.URLField(
        blank=True
    )


    class Meta:
        ordering = [
            "organization__name"
        ]


    def __str__(self):
        return f"{self.organization.name} ({self.sport.name})"
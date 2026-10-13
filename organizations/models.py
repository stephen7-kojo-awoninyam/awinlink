import hashlib
import secrets

from django.db import models
from django.conf import settings
from django.core.validators import RegexValidator
from django.utils import timezone


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
# ORGANIZATION MEMBERSHIP
# =====================================

class OrganizationMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = "OWNER", "Owner"
        MANAGER = "MANAGER", "Manager"
        RECRUITER = "RECRUITER", "Recruiter"
        VIEWER = "VIEWER", "Viewer"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        REMOVED = "REMOVED", "Removed"
        SUSPENDED = "SUSPENDED", "Suspended"

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="organization_memberships",
    )
    role = models.CharField(max_length=20, choices=Role.choices, default="VIEWER")
    status = models.CharField(max_length=20, choices=Status.choices, default="ACTIVE")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "user"],
                name="organizations_membership_org_user_unique",
            ),
            models.UniqueConstraint(
                fields=["organization"],
                condition=models.Q(role="OWNER", status="ACTIVE"),
                name="organizations_membership_one_active_owner",
            ),
            models.CheckConstraint(
                condition=models.Q(role__in=["OWNER", "MANAGER", "RECRUITER", "VIEWER"]),
                name="organizations_membership_role_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["ACTIVE", "REMOVED", "SUSPENDED"]),
                name="organizations_membership_status_valid",
            ),
        ]

    def __str__(self):
        return f"{self.organization_id}/{self.user_id}: {self.role} ({self.status})"


# =====================================
# ORGANIZATION TEAM INVITATION
# =====================================

class OrganizationTeamInvitation(models.Model):
    Role = OrganizationMembership.Role

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACCEPTED = "ACCEPTED", "Accepted"
        DECLINED = "DECLINED", "Declined"
        REVOKED = "REVOKED", "Revoked"
        EXPIRED = "EXPIRED", "Expired"

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="team_invitations",
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="received_organization_team_invitations",
    )
    inviter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="sent_organization_team_invitations",
    )
    role = models.CharField(max_length=20, choices=Role.choices, default="VIEWER")
    status = models.CharField(max_length=20, choices=Status.choices, default="PENDING")
    expires_at = models.DateTimeField()
    token_hash = models.CharField(
        max_length=64, unique=True, editable=False,
        validators=[RegexValidator(r"\A[0-9a-f]{64}\Z", "Enter a SHA-256 token digest.")],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(role__in=["OWNER", "MANAGER", "RECRUITER", "VIEWER"]),
                name="organizations_team_invite_role_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["PENDING", "ACCEPTED", "DECLINED", "REVOKED", "EXPIRED"]),
                name="organizations_team_invite_status_valid",
            ),
        ]

    def generate_token(self):
        """Set the digest and return a fresh token once, without saving it."""
        token = secrets.token_urlsafe(32)
        self.token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return token

    def check_token(self, token):
        """Only pending, unexpired invitations can authenticate a token."""
        if (
            not isinstance(token, str) or not token or not self.token_hash
            or self.status != self.Status.PENDING or self.expires_at is None
            or self.expires_at <= timezone.now()
        ):
            return False
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return secrets.compare_digest(self.token_hash, digest)

    def __str__(self):
        return f"{self.organization_id}/{self.recipient_id}: {self.role} ({self.status})"


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

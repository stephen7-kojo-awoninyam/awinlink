from django.db import models
from django.contrib.auth.models import AbstractUser
# Create your models here.


from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower


class User(AbstractUser):

    # Private, canonical account age. Existing accounts remain explicitly unknown.
    date_of_birth = models.DateField(null=True, blank=True, editable=False)
    birth_date_source = models.CharField(max_length=24, blank=True, default="", editable=False)

    @property
    def age_group(self):
        from .age_policy import age_group
        return age_group(self.date_of_birth)

    def get_full_name(self):
        # Shared notifications, classroom presence and call events use a minor's public handle.
        if self.age_group in {"CHILD", "TEEN"}:
            return self.username
        return super().get_full_name()

    terms_accepted_version = models.CharField(max_length=64, blank=True, default="", editable=False)
    terms_accepted_at = models.DateTimeField(null=True, blank=True, editable=False)

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
    
    organization_username = models.CharField(
    max_length=150,
    unique=True,
    blank=True,
    null=True
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

    class Meta(AbstractUser.Meta):
        constraints = [
            models.UniqueConstraint(
                Lower("username"),
                name="accounts_user_username_ci_unique",
            ),
        ]

    def __str__(self):
        return f"{self.username} - {self.role}"


class GoogleIdentity(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="google_identity")
    subject = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)


class GuardianAuthorization(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending guardian approval"
        APPROVED = "APPROVED", "Approved"
        REVOKED = "REVOKED", "Revoked"

    child = models.OneToOneField(User, on_delete=models.CASCADE, related_name="guardian_authorization")
    nominated_email = models.EmailField(editable=False)
    guardian = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="managed_children", editable=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, editable=False)
    verified_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="guardian_verifications", editable=False)
    verified_at = models.DateTimeField(null=True, blank=True, editable=False)
    verification_reference = models.CharField(max_length=200, blank=True, editable=False)
    consent_version = models.CharField(max_length=64, blank=True, editable=False)
    consented_at = models.DateTimeField(null=True, blank=True, editable=False)
    revoked_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        permissions = [("verify_guardianauthorization", "Can verify adult guardian identity and relationship")]
        constraints = [
            models.CheckConstraint(condition=~models.Q(child=models.F("guardian")), name="guardian_not_child"),
            models.CheckConstraint(
                condition=~models.Q(status="APPROVED") | (
                    models.Q(guardian__isnull=False, verified_by__isnull=False, verified_at__isnull=False,
                             consented_at__isnull=False, revoked_at__isnull=True) & ~models.Q(consent_version="")),
                name="guardian_approval_requires_verification"),
        ]


class GuardianAuditEvent(models.Model):
    authorization = models.ForeignKey(GuardianAuthorization, on_delete=models.CASCADE, related_name="audit_events")
    actor = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=24)
    created_at = models.DateTimeField(auto_now_add=True)


class GuardianContactPermission(models.Model):
    authorization = models.ForeignKey(GuardianAuthorization, on_delete=models.CASCADE, related_name="contact_permissions")
    contact = models.ForeignKey(User, on_delete=models.CASCADE, related_name="minor_contact_permissions")
    allow_calls = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["authorization", "contact"], name="unique_guardian_contact")]


class GuardianCoursePermission(models.Model):
    authorization = models.ForeignKey(GuardianAuthorization, on_delete=models.CASCADE, related_name="course_permissions")
    course = models.ForeignKey("learning.Course", on_delete=models.CASCADE, related_name="guardian_permissions")
    allow_live = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["authorization", "course"], name="unique_guardian_course")]


class GoogleAuthAttempt(models.Model):
    purpose = models.CharField(max_length=16, default="LOGIN", choices=[("LOGIN", "Sign in or link"), ("DELETE", "Account deletion")])
    reauth_user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    reauth_auth_hash = models.CharField(max_length=64, blank=True)
    state = models.CharField(max_length=64, unique=True)
    nonce = models.CharField(max_length=64)
    verifier = models.CharField(max_length=128)
    mobile_secret_hash = models.CharField(max_length=64, blank=True, db_index=True)
    mobile_handoff_hash = models.CharField(max_length=64, blank=True)
    link_user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE)
    status = models.CharField(max_length=16, default="PENDING")
    claims = models.JSONField(default=dict)
    expires_at = models.DateTimeField(db_index=True)


class UserBlock(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocked_accounts')
    blocked_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocked_by_accounts')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'blocked_user'], name='unique_user_block'),
            models.CheckConstraint(condition=~models.Q(user=models.F('blocked_user')), name='no_self_block'),
        ]


class ContentReport(models.Model):
    reporter = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    target_type = models.CharField(max_length=16, choices=[('user', 'User'), ('post', 'Post'), ('message', 'Message')])
    target_id = models.PositiveBigIntegerField()
    reason = models.CharField(max_length=32, choices=[('spam', 'Spam'), ('harassment', 'Harassment'), ('unsafe', 'Unsafe content'), ('other', 'Other')])
    details = models.TextField(blank=True, max_length=2000)
    status = models.CharField(max_length=16, default='OPEN', choices=[('OPEN', 'Open'), ('REVIEWED', 'Reviewed'), ('RESOLVED', 'Resolved')])
    created_at = models.DateTimeField(auto_now_add=True)

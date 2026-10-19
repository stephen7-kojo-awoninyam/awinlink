from django.db import models
from django.contrib.auth.models import AbstractUser
# Create your models here.


from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower


class User(AbstractUser):

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


class GoogleAuthAttempt(models.Model):
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

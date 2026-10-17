from django.db import models
from django.contrib.auth.models import AbstractUser
# Create your models here.


from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower


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

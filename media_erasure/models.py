from django.db import models
from django.utils import timezone


class MediaErasureJob(models.Model):
    class State(models.TextChoices):
        PENDING = 'PENDING', 'Retention period pending'
        HELD = 'HELD', 'Legal hold active'
        SHARED = 'SHARED', 'Still referenced'
        UNRESOLVED = 'UNRESOLVED', 'Provider identity unresolved'
        READY = 'READY', 'Eligible for separately approved erasure'
        ERASED = 'ERASED', 'Physical erasure confirmed'
        FAILED = 'FAILED', 'Erasure failed; retry required'

    storage_name = models.CharField(max_length=1024)
    storage_kind = models.CharField(max_length=16, choices=(('LOCAL', 'Local'), ('CLOUDINARY', 'Cloudinary')))
    provider_cloud_name = models.CharField(max_length=100, blank=True)
    resource_type = models.CharField(max_length=12, blank=True)
    delivery_type = models.CharField(max_length=16, blank=True)
    provider_asset_id = models.CharField(max_length=128, blank=True)
    identity_verified_at = models.DateTimeField(null=True, blank=True)
    identity_verified_by_id = models.BigIntegerField(null=True, blank=True)
    source_model = models.CharField(max_length=100)
    source_pk = models.CharField(max_length=64)
    source_field = models.CharField(max_length=100)
    requested_by_id = models.BigIntegerField(null=True, blank=True)
    requested_at = models.DateTimeField(default=timezone.now, editable=False)
    retain_until = models.DateTimeField(db_index=True)
    state = models.CharField(max_length=16, choices=State.choices, default=State.PENDING, db_index=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_reason = models.CharField(max_length=80, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    erased_at = models.DateTimeField(null=True, blank=True)
    erased_by_id = models.BigIntegerField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=('storage_name', 'source_model', 'source_pk', 'source_field'),
            name='media_erasure_source_once',
        )]
        indexes = [
            models.Index(fields=('state', 'retain_until', 'id'), name='media_erase_due_idx'),
            models.Index(fields=('last_checked_at', 'retain_until', 'id'), name='media_erase_check_idx'),
        ]

    def __str__(self):
        return f'{self.source_model}:{self.source_pk}.{self.source_field} ({self.state})'


class MediaLegalHold(models.Model):
    storage_name = models.CharField(max_length=1024, db_index=True)
    provider_asset_id = models.CharField(max_length=128, blank=True)
    reason = models.CharField(max_length=500)
    held = models.BooleanField(default=True, db_index=True)
    placed_by_id = models.BigIntegerField(null=True, blank=True)
    placed_at = models.DateTimeField(auto_now_add=True)
    released_by_id = models.BigIntegerField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=('held', 'storage_name'), name='media_hold_name_idx')]

    def __str__(self):
        return f'{self.storage_name} (held={self.held})'

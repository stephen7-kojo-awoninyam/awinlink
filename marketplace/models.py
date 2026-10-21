import uuid

from django.conf import settings
from django.db import models
from django.db.models.functions import Round
from talents.models import TalentProfile
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators


class Listing(models.Model):
    talent = models.ForeignKey(TalentProfile, on_delete=models.CASCADE, related_name="market_listings")
    ecosystem = models.CharField(max_length=30, choices=TalentProfile.TALENT_CATEGORY_CHOICES)
    subecosystem = models.ForeignKey("domains.TalentDomain", on_delete=models.PROTECT)
    title = models.CharField(max_length=200)
    description = models.TextField(max_length=5000)
    status = models.CharField(max_length=12, choices=[("DRAFT", "Draft"), ("PUBLISHED", "Published"), ("PAUSED", "Paused")], default="DRAFT")
    publication_consented_at = models.DateTimeField(null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    pricing_mode = models.CharField(max_length=12, default='QUOTE_ONLY', choices=[(x, x) for x in ['QUOTE_ONLY', 'FIXED', 'HOURLY']])
    base_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default='GHS')
    duration_minutes = models.PositiveIntegerField(default=60)
    buffer_minutes = models.PositiveIntegerField(default=0)
    booking_enabled = models.BooleanField(default=False)
    revision = models.PositiveIntegerField(default=1, editable=False)

    class Meta:
        ordering = ["-created_at", "-pk"]

        constraints = [
            models.CheckConstraint(condition=models.Q(status__in=["DRAFT", "PUBLISHED", "PAUSED"]), name="market_listing_valid_status"),
            models.CheckConstraint(condition=~models.Q(status="PUBLISHED") | models.Q(publication_consented_at__isnull=False), name="market_listing_publication_consent"),
            models.CheckConstraint(condition=(models.Q(pricing_mode='QUOTE_ONLY', base_price__isnull=True) | models.Q(pricing_mode__in=['FIXED', 'HOURLY'], base_price__isnull=False, base_price__gt=0, base_price__lte='9999999999.99')), name='market_listing_price_valid'),
            models.CheckConstraint(condition=models.Q(duration_minutes__gte=1, duration_minutes__lte=1440, buffer_minutes__lte=240), name='market_listing_duration_valid'),
        ]


class Offer(models.Model):
    listing = models.ForeignKey(Listing, on_delete=models.PROTECT, related_name="offers")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="market_offers")
    organization = models.ForeignKey("organizations.Organization", null=True, blank=True, on_delete=models.PROTECT)
    terms = models.TextField(max_length=5000)
    status = models.CharField(max_length=12, default="PENDING", choices=[(s, s.title()) for s in ("PENDING", "ACCEPTED", "DECLINED", "WITHDRAWN")])
    talent_consented_at = models.DateTimeField(null=True, editable=False)
    decided_at = models.DateTimeField(null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    workflow_version = models.PositiveSmallIntegerField(default=1, editable=False)
    listing_revision = models.PositiveIntegerField(null=True, editable=False)
    quoted_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, editable=False)
    quoted_currency = models.CharField(max_length=3, null=True, editable=False)
    requested_start = models.DateTimeField(null=True, editable=False)
    requested_end = models.DateTimeField(null=True, editable=False)
    quote_snapshot = models.JSONField(default=dict, editable=False)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.UniqueConstraint(fields=["listing", "sender"], condition=models.Q(status="PENDING", organization__isnull=True), name="market_pending_personal_offer"),
            models.UniqueConstraint(fields=["listing", "organization"], condition=models.Q(status="PENDING", organization__isnull=False), name="market_pending_org_offer"),
            models.CheckConstraint(condition=models.Q(status__in=["PENDING", "ACCEPTED", "DECLINED", "WITHDRAWN"]), name="market_offer_valid_status"),
            models.CheckConstraint(condition=(models.Q(status="PENDING", decided_at__isnull=True, talent_consented_at__isnull=True) | models.Q(status="ACCEPTED", decided_at__isnull=False, talent_consented_at__isnull=False) | models.Q(status__in=["DECLINED", "WITHDRAWN"], decided_at__isnull=False, talent_consented_at__isnull=True)), name="market_offer_decision_consent"),
            models.CheckConstraint(condition=(models.Q(workflow_version=1, quoted_amount__isnull=True, quoted_currency__isnull=True, requested_start__isnull=True, requested_end__isnull=True, listing_revision__isnull=True) | models.Q(workflow_version=2, quoted_amount__isnull=False, quoted_amount__gt=0, quoted_amount__lte='9999999999.99', quoted_currency__isnull=False, listing_revision__isnull=False, requested_start__isnull=False, requested_end__isnull=False, requested_end__gt=models.F('requested_start'))), name='market_offer_quote_valid'),
        ]


class DealMessage(models.Model):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    body = models.TextField(max_length=3000)
    created_at = models.DateTimeField(auto_now_add=True)
    scope = models.CharField(max_length=12, default='NEGOTIATION', choices=[('NEGOTIATION', 'Negotiation'), ('FULFILLMENT', 'Fulfillment')])

    class Meta:
        ordering = ["created_at", "pk"]
        constraints = [models.CheckConstraint(condition=models.Q(scope__in=['NEGOTIATION', 'FULFILLMENT']), name='market_message_scope_valid')]


class AvailabilityWindow(models.Model):
    talent = models.ForeignKey(TalentProfile, on_delete=models.CASCADE, related_name='market_availability')
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    timezone = models.CharField(max_length=64, default='UTC')

    class Meta:
        ordering = ['starts_at', 'pk']
        indexes = [models.Index(fields=['talent', 'starts_at', 'ends_at'])]
        constraints = [models.CheckConstraint(condition=models.Q(ends_at__gt=models.F('starts_at')), name='market_availability_order')]


class Booking(models.Model):
    STATUSES = ['CONFIRMED', 'IN_PROGRESS', 'SUBMITTED', 'COMPLETED', 'CANCELLED']
    offer = models.OneToOneField(Offer, on_delete=models.PROTECT, related_name='booking')
    talent = models.ForeignKey(TalentProfile, on_delete=models.PROTECT, related_name='market_bookings')
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    busy_start = models.DateTimeField()
    busy_end = models.DateTimeField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    snapshot = models.JSONField(default=dict)
    status = models.CharField(max_length=12, default='CONFIRMED', choices=[(x, x) for x in STATUSES])
    started_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)
    cancelled_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        constraints = [
            models.CheckConstraint(condition=models.Q(status__in=['CONFIRMED', 'IN_PROGRESS', 'SUBMITTED', 'COMPLETED', 'CANCELLED']), name='market_booking_status_valid'),
            models.CheckConstraint(condition=models.Q(amount__gt=0, amount__lte='9999999999.99'), name='market_booking_amount_positive'),
            models.CheckConstraint(condition=models.Q(ends_at__gt=models.F('starts_at'), busy_start__lte=models.F('starts_at'), busy_end__gte=models.F('ends_at')), name='market_booking_interval_valid'),
            models.CheckConstraint(condition=(models.Q(status='CONFIRMED', started_at__isnull=True, completed_at__isnull=True, cancelled_at__isnull=True) | models.Q(status__in=['IN_PROGRESS', 'SUBMITTED'], started_at__isnull=False, completed_at__isnull=True, cancelled_at__isnull=True) | models.Q(status='COMPLETED', started_at__isnull=False, completed_at__isnull=False, cancelled_at__isnull=True) | models.Q(status='CANCELLED', started_at__isnull=True, completed_at__isnull=True, cancelled_at__isnull=False)), name='market_booking_timestamps_valid'),
            ExclusionConstraint(name='market_booking_no_overlap', expressions=[('talent', RangeOperators.EQUAL), (models.Func('busy_start', 'busy_end', models.Value('[)'), function='TSTZRANGE', output_field=DateTimeRangeField()), RangeOperators.OVERLAPS)], condition=~models.Q(status='CANCELLED')),
        ]


class FulfillmentSubmission(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name='submissions')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    sequence = models.PositiveIntegerField()
    summary = models.TextField(max_length=10000)
    artifact_name = models.CharField(max_length=200, blank=True)
    artifact = models.BinaryField(null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sequence']
        constraints = [models.UniqueConstraint(fields=['booking', 'sequence'], name='market_submission_sequence_unique')]


class BookingEvent(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name='events')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=30)
    reason = models.TextField(max_length=3000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']


class BookingReview(models.Model):
    booking = models.OneToOneField(Booking, on_delete=models.PROTECT, related_name='review')
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    rating = models.PositiveSmallIntegerField()
    text = models.TextField(max_length=3000)
    publication_consented_at = models.DateTimeField(null=True)
    moderation_state = models.CharField(max_length=10, default='VISIBLE', choices=[('VISIBLE', 'Visible'), ('HIDDEN', 'Hidden')])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        constraints = [models.CheckConstraint(condition=models.Q(rating__gte=1, rating__lte=5), name='market_review_rating_valid'), models.CheckConstraint(condition=models.Q(moderation_state__in=['VISIBLE', 'HIDDEN']), name='market_review_moderation_valid')]


class MarketInvoice(models.Model):
    booking = models.OneToOneField(Booking, on_delete=models.PROTECT, related_name='invoice')
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status = models.CharField(max_length=20, default='ISSUED', choices=[(s, s) for s in ['ISSUED', 'PARTIALLY_CREDITED', 'CREDITED', 'VOID']])
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    fee_bps = models.PositiveSmallIntegerField()
    fee_amount = models.DecimalField(max_digits=12, decimal_places=2)
    talent_amount = models.DecimalField(max_digits=12, decimal_places=2)
    credited_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    credited_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    snapshot = models.JSONField(default=dict, editable=False)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    issued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-pk']
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0, amount__lte='9999999999.99', fee_bps__lte=10000,
                fee_amount__gte=0, fee_amount__lte=models.F('amount'), talent_amount__gte=0,
                amount=Round(models.F('fee_amount') + models.F('talent_amount'), 2)), name='market_invoice_totals_valid'),
            models.CheckConstraint(condition=models.Q(credited_amount__gte=0, credited_amount__lte=models.F('amount'),
                credited_fee__gte=0, credited_fee__lte=models.F('fee_amount')) & models.Q(credited_fee__lte=models.F('credited_amount')),
                name='market_invoice_credits_valid'),
            models.CheckConstraint(condition=(models.Q(status__in=['ISSUED', 'VOID'], credited_amount=0, credited_fee=0)
                | models.Q(status='PARTIALLY_CREDITED', credited_amount__gt=0, credited_amount__lt=models.F('amount'))
                | models.Q(status='CREDITED', credited_amount=models.F('amount'), credited_fee=models.F('fee_amount'))),
                name='market_invoice_status_valid'),
        ]


class MarketRefund(models.Model):
    invoice = models.ForeignKey(MarketInvoice, on_delete=models.PROTECT, related_name='refunds')
    idempotency_key = models.UUIDField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.TextField(max_length=3000)
    status = models.CharField(max_length=10, default='PENDING', choices=[(s, s) for s in ['PENDING', 'APPROVED', 'REJECTED']])
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+', null=True)
    decision_reason = models.TextField(max_length=3000, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ['pk']
        constraints = [
            models.UniqueConstraint(fields=['invoice', 'idempotency_key'], name='market_refund_request_unique'),
            models.CheckConstraint(condition=models.Q(amount__gt=0, amount__lte='9999999999.99'), name='market_refund_amount_valid'),
            models.CheckConstraint(condition=(models.Q(status='PENDING', decided_by__isnull=True, decided_at__isnull=True)
                | models.Q(status__in=['APPROVED', 'REJECTED'], decided_by__isnull=False, decided_at__isnull=False)),
                name='market_refund_decision_valid'),
        ]


class MarketTransaction(models.Model):
    """Append-only service records of obligations/credits; never a cash ledger."""
    invoice = models.ForeignKey(MarketInvoice, on_delete=models.PROTECT, related_name='transactions')
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    refund = models.OneToOneField(MarketRefund, on_delete=models.PROTECT, null=True, related_name='transaction_record')
    kind = models.CharField(max_length=20, choices=[(s, s) for s in ['INVOICE_ISSUED', 'REFUND_APPROVED', 'INVOICE_VOIDED']])
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    fee_amount = models.DecimalField(max_digits=12, decimal_places=2)
    talent_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.TextField(max_length=3000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['pk']
        constraints = [
            models.UniqueConstraint(fields=['invoice', 'kind'], condition=~models.Q(kind='REFUND_APPROVED'), name='market_invoice_event_unique'),
            models.CheckConstraint(condition=(models.Q(kind='REFUND_APPROVED', refund__isnull=False)
                | models.Q(kind__in=['INVOICE_ISSUED', 'INVOICE_VOIDED'], refund__isnull=True)), name='market_transaction_kind_valid'),
            models.CheckConstraint(condition=models.Q(amount__gt=0, amount__lte='9999999999.99', fee_amount__gte=0,
                talent_amount__gte=0, amount=Round(models.F('fee_amount') + models.F('talent_amount'), 2)), name='market_transaction_totals_valid'),
        ]

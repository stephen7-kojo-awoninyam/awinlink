from decimal import Decimal

from cloudinary.models import CloudinaryField
from django.conf import settings
from django.core.validators import MinValueValidator, URLValidator
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Count, F, Q, Sum
from django.utils import timezone


class Campaign(models.Model):
    STATUS_CHOICES = (
        ("DRAFT", "Draft"),
        ("PENDING_REVIEW", "Pending review"),
        ("APPROVED", "Approved"),
        ("ACTIVE", "Active"),
        ("PAUSED", "Paused"),
        ("REJECTED", "Rejected"),
        ("COMPLETED", "Completed"),
        ("CANCELLED", "Cancelled"),
    )
    BILLING_CHOICES = (
        ("CPM", "Cost per thousand impressions"),
        ("CPC", "Cost per click"),
    )
    CATEGORY_CHOICES = (
        ("SPORTS", "Sports"),
        ("SCIENCE_TECHNOLOGY", "Science & Technology"),
        ("ARTS", "Arts"),
        ("OTHERS", "Others"),
    )

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="advertising_campaigns",
    )
    name = models.CharField(max_length=150)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="DRAFT",
        db_index=True,
    )
    billing_model = models.CharField(
        max_length=3,
        choices=BILLING_CHOICES,
        default="CPM",
    )
    currency = models.CharField(
        max_length=3,
        default=getattr(settings, "ADVERTISING_CURRENCY", "GHS"),
    )
    total_budget = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )
    daily_budget = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    cost_per_thousand_impressions = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("1.00"),
        validators=(MinValueValidator(Decimal("0.01")),),
    )
    cost_per_click = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.10"),
        validators=(MinValueValidator(Decimal("0.01")),),
    )
    target_categories = models.JSONField(default=list, blank=True)
    domains = models.ManyToManyField(
        "domains.TalentDomain",
        blank=True,
        related_name="advertising_campaigns",
    )
    sports = models.ManyToManyField(
        "sports.Sport",
        blank=True,
        related_name="advertising_campaigns",
    )
    skills = models.ManyToManyField(
        "skills.Skill",
        blank=True,
        related_name="advertising_campaigns",
    )
    frequency_cap = models.PositiveSmallIntegerField(
        default=3,
        validators=(MinValueValidator(1),),
        help_text="Maximum impressions per user in the selected frequency window.",
    )
    frequency_window_hours = models.PositiveSmallIntegerField(
        default=24,
        validators=(MinValueValidator(1),),
    )
    priority = models.PositiveSmallIntegerField(default=0)
    review_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(total_budget__gt=0),
                name="advertising_campaign_budget_positive",
            ),
            models.CheckConstraint(
                condition=Q(end_date__gte=models.F("start_date")),
                name="advertising_campaign_dates_ordered",
            ),
            models.CheckConstraint(
                condition=Q(frequency_cap__gt=0)
                & Q(frequency_window_hours__gt=0),
                name="advertising_campaign_frequency_positive",
            ),
            models.CheckConstraint(
                condition=Q(cost_per_thousand_impressions__gt=0)
                & Q(cost_per_click__gt=0),
                name="advertising_campaign_rates_positive",
            ),
            models.CheckConstraint(
                condition=Q(daily_budget__isnull=True)
                | (
                    Q(daily_budget__gt=0)
                    & Q(daily_budget__lte=F("total_budget"))
                ),
                name="advertising_campaign_daily_budget_valid",
            ),
        ]

    def __str__(self):
        return self.name

    def _event_counts(self, since=None):
        events = AdvertisementEvent.objects.filter(advertisement__campaign=self)
        if since is not None:
            events = events.filter(created_at__gte=since)
        return events.aggregate(
            impressions=Count("id", filter=Q(event_type="IMPRESSION")),
            clicks=Count("id", filter=Q(event_type="CLICK")),
        )

    def calculate_spend(self, since=None):
        counts = self._event_counts(since)
        if self.billing_model == "CPM":
            return (
                Decimal(counts["impressions"])
                * Decimal(str(self.cost_per_thousand_impressions))
                / Decimal("1000")
            )
        return Decimal(counts["clicks"]) * Decimal(str(self.cost_per_click))

    @property
    def funded_amount(self):
        total = self.payments.filter(status="SUCCESS").aggregate(
            total=Sum("amount")
        )["total"]
        return Decimal(str(total)) if total is not None else Decimal("0.00")

    @property
    def reserved_amount(self):
        total = self.payments.filter(status="PENDING").aggregate(
            total=Sum("amount")
        )["total"]
        return Decimal(str(total)) if total is not None else Decimal("0.00")

    @property
    def remaining_to_fund(self):
        return max(
            Decimal("0.00"),
            Decimal(str(self.total_budget))
            - self.funded_amount
            - self.reserved_amount,
        )

    @property
    def spent_amount(self):
        return self.calculate_spend()

    @property
    def remaining_budget(self):
        return max(
            Decimal("0.00"),
            min(Decimal(str(self.total_budget)), self.funded_amount)
            - self.spent_amount,
        )

    @property
    def available_daily_budget(self):
        if self.daily_budget is None:
            return self.remaining_budget
        start_of_day = timezone.localtime().replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        return max(
            Decimal("0.00"),
            min(
                Decimal(str(self.daily_budget))
                - self.calculate_spend(start_of_day),
                self.remaining_budget,
            ),
        )

    def can_deliver(self, on_date=None):
        on_date = on_date or timezone.localdate()
        if not self.is_running(on_date):
            return False
        next_cost = (
            Decimal(str(self.cost_per_click))
            if self.billing_model == "CPC"
            else Decimal(str(self.cost_per_thousand_impressions))
            / Decimal("1000")
        )
        return self.remaining_budget >= next_cost and self.available_daily_budget >= next_cost

    def is_running(self, on_date=None):
        on_date = on_date or timezone.localdate()
        return (
            self.status == "ACTIVE"
            and self.start_date <= on_date <= self.end_date
        )

    def can_record_click(self):
        if not self.is_running():
            return False
        if self.billing_model == "CPM":
            return True
        return (
            self.remaining_budget >= Decimal(str(self.cost_per_click))
            and self.available_daily_budget >= Decimal(str(self.cost_per_click))
        )

    def clean(self):
        super().clean()
        if self.status == "REJECTED" and not self.review_note.strip():
            raise ValidationError(
                {"review_note": "A review note is required when rejecting a campaign."}
            )
        if self.pk:
            existing = Campaign.objects.filter(pk=self.pk).first()
            if existing and existing.currency != self.currency and self.payments.exists():
                raise ValidationError(
                    {"currency": "Currency cannot change after campaign payments exist."}
                )
            if self.total_budget < self.funded_amount + self.reserved_amount:
                raise ValidationError(
                    {"total_budget": "Budget cannot be lower than paid or pending funding."}
                )


class Advertisement(models.Model):
    campaign = models.OneToOneField(
        Campaign,
        on_delete=models.CASCADE,
        related_name="advertisement",
    )
    title = models.CharField(max_length=120)
    body = models.TextField(blank=True)
    image = CloudinaryField(
        "image",
        resource_type="image",
        blank=True,
        null=True,
    )
    video = CloudinaryField(
        "video",
        resource_type="video",
        blank=True,
        null=True,
    )
    cta_label = models.CharField(max_length=40, default="Learn more")
    destination_url = models.URLField(
        max_length=500,
        validators=(URLValidator(schemes=("https",)),),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class CampaignPayment(models.Model):
    STATUS_CHOICES = (
        ("PENDING", "Pending"),
        ("SUCCESS", "Successful"),
        ("FAILED", "Failed"),
    )

    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    reference = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="PENDING",
        db_index=True,
    )
    authorization_url = models.URLField(max_length=500, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="advertising_payment_amount_positive",
            ),
        ]

    def clean(self):
        super().clean()
        if self.campaign_id and self.currency != self.campaign.currency:
            raise ValidationError(
                {"currency": "Payment currency must match the campaign currency."}
            )

    def __str__(self):
        return f"{self.reference} ({self.status})"


class AdvertisementEvent(models.Model):
    EVENT_CHOICES = (
        ("IMPRESSION", "Impression"),
        ("CLICK", "Click"),
        ("VIDEO_VIEW", "Video view"),
    )

    advertisement = models.ForeignKey(
        Advertisement,
        on_delete=models.CASCADE,
        related_name="events",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="advertisement_events",
    )
    event_type = models.CharField(max_length=12, choices=EVENT_CHOICES, db_index=True)
    tracking_id = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(
                fields=("advertisement", "user", "event_type", "created_at"),
                name="ad_event_frequency_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("advertisement", "user", "event_type", "tracking_id"),
                condition=~Q(tracking_id=""),
                name="advertising_event_tracking_unique",
            ),
        ]

    def __str__(self):
        return f"{self.advertisement_id} {self.event_type}"

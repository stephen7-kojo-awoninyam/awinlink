from django.conf import settings
from django.db import models
from talents.models import TalentProfile


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

    class Meta:
        ordering = ["-created_at", "-pk"]

        constraints = [
            models.CheckConstraint(condition=models.Q(status__in=["DRAFT", "PUBLISHED", "PAUSED"]), name="market_listing_valid_status"),
            models.CheckConstraint(condition=~models.Q(status="PUBLISHED") | models.Q(publication_consented_at__isnull=False), name="market_listing_publication_consent"),
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

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.UniqueConstraint(fields=["listing", "sender"], condition=models.Q(status="PENDING", organization__isnull=True), name="market_pending_personal_offer"),
            models.UniqueConstraint(fields=["listing", "organization"], condition=models.Q(status="PENDING", organization__isnull=False), name="market_pending_org_offer"),
            models.CheckConstraint(condition=models.Q(status__in=["PENDING", "ACCEPTED", "DECLINED", "WITHDRAWN"]), name="market_offer_valid_status"),
            models.CheckConstraint(condition=(models.Q(status="PENDING", decided_at__isnull=True, talent_consented_at__isnull=True) | models.Q(status="ACCEPTED", decided_at__isnull=False, talent_consented_at__isnull=False) | models.Q(status__in=["DECLINED", "WITHDRAWN"], decided_at__isnull=False, talent_consented_at__isnull=True)), name="market_offer_decision_consent"),
        ]


class DealMessage(models.Model):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    body = models.TextField(max_length=3000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]

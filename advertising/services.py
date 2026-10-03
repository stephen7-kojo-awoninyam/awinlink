import hashlib
import uuid
from datetime import timedelta

from django.core import signing
from django.core.signing import BadSignature
from django.db import transaction
from django.utils import timezone

from sports.models import SportsTalentProfile
from talents.models import TalentProfile

from .models import Advertisement, AdvertisementEvent, Campaign


class CampaignTransitionError(ValueError):
    pass


class InvalidTrackingToken(ValueError):
    pass


def create_tracking_token(advertisement_id, user_id):
    return signing.dumps(
        {
            "advertisement_id": advertisement_id,
            "user_id": user_id,
            "nonce": uuid.uuid4().hex,
        },
        salt="advertising.event",
    )


def _tracking_id(advertisement_id, user, token):
    try:
        payload = signing.loads(
            token,
            salt="advertising.event",
            max_age=24 * 60 * 60,
        )
    except BadSignature as exc:
        raise InvalidTrackingToken("Invalid or expired ad tracking token.") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("advertisement_id") != advertisement_id
        or payload.get("user_id") != user.pk
        or not payload.get("nonce")
    ):
        raise InvalidTrackingToken("Ad tracking token does not match this user or ad.")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@transaction.atomic
def transition_campaign(campaign_id, actor, new_status, review_note=""):
    campaign = Campaign.objects.select_for_update().get(pk=campaign_id)
    is_admin = actor.is_staff or actor.is_superuser
    owns_campaign = campaign.organization.user_id == actor.pk

    if new_status == "PENDING_REVIEW":
        if not owns_campaign or campaign.status not in {"DRAFT", "REJECTED"}:
            raise CampaignTransitionError("This campaign cannot be submitted.")
        if not Advertisement.objects.filter(campaign=campaign).exists():
            raise CampaignTransitionError(
                "Add an advertisement before submitting the campaign."
            )
    elif new_status in {"APPROVED", "REJECTED"}:
        if not is_admin or campaign.status != "PENDING_REVIEW":
            raise CampaignTransitionError("Only admins can review submitted campaigns.")
        if new_status == "REJECTED" and not review_note.strip():
            raise CampaignTransitionError("A rejection note is required.")
    elif new_status == "ACTIVE":
        if not owns_campaign or campaign.status != "APPROVED":
            raise CampaignTransitionError(
                "Only an approved campaign can be activated by its owner."
            )
        next_cost = (
            campaign.cost_per_click
            if campaign.billing_model == "CPC"
            else campaign.cost_per_thousand_impressions / 1000
        )
        if (
            campaign.remaining_budget < next_cost
            or campaign.available_daily_budget < next_cost
        ):
            raise CampaignTransitionError("Fund the campaign before activating it.")
    elif new_status == "PAUSED":
        if not owns_campaign or campaign.status != "ACTIVE":
            raise CampaignTransitionError("Only an active campaign can be paused.")
    elif new_status == "CANCELLED":
        if not (owns_campaign or is_admin) or campaign.status in {
            "COMPLETED",
            "CANCELLED",
        }:
            raise CampaignTransitionError("This campaign cannot be cancelled.")
    else:
        raise CampaignTransitionError("Unsupported campaign status transition.")

    campaign.status = new_status
    campaign.review_note = review_note.strip()
    campaign.save(update_fields=("status", "review_note", "updated_at"))
    return campaign


def _campaign_matches_profile(campaign, profile, domain_ids, skill_ids, sport_ids):
    if not profile:
        return False
    if campaign.target_categories and profile.talent_category not in campaign.target_categories:
        return False
    if campaign.domains.exists() and not domain_ids.intersection(
        campaign.domains.values_list("pk", flat=True)
    ):
        return False
    if campaign.skills.exists() and not skill_ids.intersection(
        campaign.skills.values_list("pk", flat=True)
    ):
        return False
    if campaign.sports.exists() and not sport_ids.intersection(
        campaign.sports.values_list("pk", flat=True)
    ):
        return False
    return True


def _within_frequency_cap(campaign, user, now):
    window_start = now - timedelta(hours=campaign.frequency_window_hours)
    recent_impressions = AdvertisementEvent.objects.filter(
        advertisement__campaign=campaign,
        user=user,
        event_type="IMPRESSION",
        created_at__gte=window_start,
    ).count()
    return recent_impressions < campaign.frequency_cap


@transaction.atomic
def record_ad_event(advertisement_id, user, event_type, token):
    advertisement = Advertisement.objects.select_related("campaign").get(
        pk=advertisement_id
    )
    tracking_id = _tracking_id(advertisement_id, user, token)
    campaign = Campaign.objects.select_for_update().get(
        pk=advertisement.campaign_id
    )
    if AdvertisementEvent.objects.filter(
        advertisement=advertisement,
        user=user,
        event_type=event_type,
        tracking_id=tracking_id,
    ).exists():
        return False
    now = timezone.now()
    if event_type == "IMPRESSION":
        if (
            not campaign.can_deliver()
            or not _within_frequency_cap(campaign, user, now)
        ):
            return False
    elif event_type == "CLICK":
        if not campaign.can_record_click():
            return False
    elif event_type == "VIDEO_VIEW":
        if not campaign.is_running():
            return False
    else:
        raise ValueError("Unsupported advertisement event type.")
    AdvertisementEvent.objects.create(
        advertisement=advertisement,
        user=user,
        event_type=event_type,
        tracking_id=tracking_id,
    )
    return True


def get_ads_for_user(user, limit=3):
    """Return eligible targeted ads, or general ads when no targeted match exists."""
    if limit <= 0:
        return []

    today = timezone.localdate()
    now = timezone.now()
    campaigns = list(
        Campaign.objects.filter(
            status="ACTIVE",
            start_date__lte=today,
            end_date__gte=today,
            advertisement__isnull=False,
        )
        .select_related("organization", "advertisement")
        .prefetch_related("domains", "skills", "sports")
        .order_by("-priority", "created_at")
    )
    profile = TalentProfile.objects.filter(user=user).first()
    domain_ids = (
        set(profile.domains.values_list("pk", flat=True)) if profile else set()
    )
    skill_ids = (
        set(profile.skills.values_list("pk", flat=True)) if profile else set()
    )
    sport_ids = set()
    if profile:
        sport_ids = set(
            SportsTalentProfile.objects.filter(talent=profile)
            .exclude(sport_id=None)
            .values_list("sport_id", flat=True)
        )

    deliverable = [
        campaign
        for campaign in campaigns
        if campaign.can_deliver(today)
        and _within_frequency_cap(campaign, user, now)
    ]
    targeted = [
        campaign
        for campaign in deliverable
        if campaign.target_categories
        or campaign.domains.exists()
        or campaign.skills.exists()
        or campaign.sports.exists()
    ]
    matching = [
        campaign
        for campaign in targeted
        if _campaign_matches_profile(
            campaign,
            profile,
            domain_ids,
            skill_ids,
            sport_ids,
        )
    ]
    selected = matching or [
        campaign
        for campaign in deliverable
        if not (
            campaign.target_categories
            or campaign.domains.exists()
            or campaign.skills.exists()
            or campaign.sports.exists()
        )
    ]
    return [campaign.advertisement for campaign in selected[:limit]]


def insert_ads_into_feed(feed_items, advertisements, user, interval=5):
    """Insert sponsored items without reordering the personalized feed."""
    if interval <= 0:
        raise ValueError("Feed ad interval must be greater than zero.")
    items = []
    ad_index = 0
    now = timezone.now()
    for index, item in enumerate(feed_items, start=1):
        items.append(item)
        if index % interval == 0 and ad_index < len(advertisements):
            ad = advertisements[ad_index]
            items.append(
                {
                    "type": "ADVERTISEMENT",
                    "object": ad,
                    "created_at": now,
                    "score": 0,
                    "tracking_token": create_tracking_token(ad.pk, user.pk),
                }
            )
            ad_index += 1
    while ad_index < len(advertisements):
        ad = advertisements[ad_index]
        items.append(
            {
                "type": "ADVERTISEMENT",
                "object": ad,
                "created_at": now,
                "score": 0,
                "tracking_token": create_tracking_token(ad.pk, user.pk),
            }
        )
        ad_index += 1
    return items

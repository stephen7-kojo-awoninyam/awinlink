import hashlib
import hmac
import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from advertising.models import (
    Advertisement,
    AdvertisementEvent,
    Campaign,
    CampaignPayment,
)
from advertising.services import create_tracking_token, get_ads_for_user
from advertising.services import transition_campaign
from domains.models import TalentDomain
from organizations.models import Organization
from skills.models import Skill, SkillCategory
from sports.models import Sport, SportsTalentProfile
from talents.models import TalentProfile


@override_settings(
    STORAGES={
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
)
class AdvertisingTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.organization_user = user_model.objects.create_user(
            username="ad_owner",
            email="owner@example.com",
            password="test-password",
            role="ORGANIZATION",
        )
        self.organization = Organization.objects.create(
            user=self.organization_user,
            name="Awinlink Advertiser",
            country="Ghana",
        )
        self.talent_user = user_model.objects.create_user(
            username="ad_talent",
            password="test-password",
            role="ATHLETE",
        )
        self.talent = TalentProfile.objects.create(
            user=self.talent_user,
            talent_category="ARTS",
        )

    def test_video_field_uses_cloudinary_video_resource_type(self):
        self.assertEqual(
            Advertisement._meta.get_field("video").resource_type,
            "video",
        )

    def test_organization_can_create_campaign_and_creative_as_a_draft(self):
        self.client.force_login(self.organization_user)
        today = timezone.localdate()

        response = self.client.post(
            reverse("advertising_campaign_create"),
            {
                "name": "Arts promotion",
                "start_date": today.isoformat(),
                "end_date": (today + timedelta(days=5)).isoformat(),
                "billing_model": "CPM",
                "total_budget": "100.00",
                "daily_budget": "",
                "cost_per_thousand_impressions": "1.00",
                "cost_per_click": "0.10",
                "target_categories": ["ARTS"],
                "domains": [],
                "sports": [],
                "skills": [],
                "frequency_cap": "3",
                "frequency_window_hours": "24",
                "title": "Arts opportunity",
                "body": "Discover the latest collection.",
                "image": "",
                "video": "",
                "cta_label": "Explore",
                "destination_url": "https://example.com/arts",
            },
        )

        self.assertRedirects(response, reverse("advertising_dashboard"))
        campaign = Campaign.objects.get(name="Arts promotion")
        self.assertEqual(campaign.status, "DRAFT")
        self.assertEqual(campaign.target_categories, ["ARTS"])
        self.assertTrue(Advertisement.objects.filter(campaign=campaign).exists())

    def test_campaign_requires_review_and_funding_before_activation(self):
        campaign, _ = self.create_campaign(
            "Approval workflow campaign",
            status="DRAFT",
        )
        CampaignPayment.objects.filter(campaign=campaign).update(status="FAILED")
        self.client.force_login(self.organization_user)
        response = self.client.post(
            reverse(
                "advertising_campaign_action",
                args=(campaign.pk, "submit"),
            )
        )
        self.assertRedirects(response, reverse("advertising_dashboard"))
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, "PENDING_REVIEW")

        admin_user = get_user_model().objects.create_superuser(
            username="ad_admin",
            email="admin@example.com",
            password="test-password",
        )
        transition_campaign(campaign.pk, admin_user, "APPROVED")
        response = self.client.post(
            reverse(
                "advertising_campaign_action",
                args=(campaign.pk, "activate"),
            )
        )
        self.assertRedirects(response, reverse("advertising_dashboard"))
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, "APPROVED")

        CampaignPayment.objects.filter(campaign=campaign).update(status="SUCCESS")
        self.client.post(
            reverse(
                "advertising_campaign_action",
                args=(campaign.pk, "activate"),
            )
        )
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, "ACTIVE")

    def create_campaign(self, name, categories=None, frequency_cap=3, status="ACTIVE"):
        today = timezone.localdate()
        campaign = Campaign.objects.create(
            organization=self.organization,
            name=name,
            start_date=today - timedelta(days=1),
            end_date=today + timedelta(days=7),
            status=status,
            total_budget="100.00",
            target_categories=categories or [],
            frequency_cap=frequency_cap,
        )
        CampaignPayment.objects.create(
            campaign=campaign,
            reference=f"ref-{name}",
            amount="100.00",
            currency=campaign.currency,
            status="SUCCESS",
        )
        ad = Advertisement.objects.create(
            campaign=campaign,
            title=f"{name} ad",
            body="A relevant offer",
            destination_url="https://example.com/offer",
        )
        return campaign, ad

    def test_targeted_campaign_is_selected_for_matching_talent_category(self):
        _, advertisement = self.create_campaign(
            "Arts campaign",
            categories=["ARTS"],
        )

        self.assertEqual(get_ads_for_user(self.talent_user), [advertisement])

    def test_domain_sport_and_skill_targets_match_talent_profile(self):
        campaign, advertisement = self.create_campaign("Multi-signal campaign")
        domain = TalentDomain.objects.create(name="Digital Media")
        skill_category = SkillCategory.objects.create(name="Creative")
        skill = Skill.objects.create(category=skill_category, name="Photography")
        sport = Sport.objects.create(name="Tennis")
        campaign.domains.add(domain)
        campaign.skills.add(skill)
        campaign.sports.add(sport)
        self.talent.domains.add(domain)
        self.talent.skills.add(skill)
        SportsTalentProfile.objects.create(talent=self.talent, sport=sport)

        self.assertEqual(get_ads_for_user(self.talent_user), [advertisement])

    def test_general_campaign_is_fallback_when_no_targeted_campaign_matches(self):
        self.create_campaign("Sports campaign", categories=["SPORTS"])
        _, general_ad = self.create_campaign("General campaign")

        self.assertEqual(get_ads_for_user(self.talent_user), [general_ad])

    def test_frequency_cap_stops_repeated_delivery(self):
        campaign, advertisement = self.create_campaign(
            "Frequency-limited campaign",
            categories=["ARTS"],
            frequency_cap=1,
        )
        self.assertEqual(get_ads_for_user(self.talent_user), [advertisement])
        AdvertisementEvent.objects.create(
            advertisement=advertisement,
            user=self.talent_user,
            event_type="IMPRESSION",
        )

        self.assertEqual(get_ads_for_user(self.talent_user), [])
        self.assertTrue(campaign.can_deliver())

    def test_home_feed_renders_and_tracks_a_sponsored_ad(self):
        self.create_campaign("Feed campaign", categories=["ARTS"])
        self.client.force_login(self.talent_user)

        response = self.client.get(reverse("home_feed"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sponsored")
        advertisement = Advertisement.objects.get(title="Feed campaign ad")
        feed_ad = next(
            item
            for item in response.context["feed_items"]
            if item["type"] == "ADVERTISEMENT"
        )
        impression_response = self.client.post(
            reverse("advertisement_impression", args=(advertisement.pk,)),
            {"token": feed_ad["tracking_token"]},
        )
        replayed_impression = self.client.post(
            reverse("advertisement_impression", args=(advertisement.pk,)),
            {"token": feed_ad["tracking_token"]},
        )
        self.assertEqual(impression_response.status_code, 200)
        self.assertEqual(replayed_impression.status_code, 409)
        self.assertEqual(
            AdvertisementEvent.objects.filter(
                user=self.talent_user,
                event_type="IMPRESSION",
            ).count(),
            1,
        )

    def test_campaign_dashboard_is_scoped_to_the_owning_organization(self):
        campaign, _ = self.create_campaign("Private campaign", categories=["ARTS"])
        other_org_user = get_user_model().objects.create_user(
            username="other_ad_owner",
            password="test-password",
            role="ORGANIZATION",
        )
        Organization.objects.create(
            user=other_org_user,
            name="Other advertiser",
            country="Ghana",
        )
        self.client.force_login(other_org_user)

        response = self.client.get(reverse("advertising_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, campaign.name)

    def test_click_is_tracked_before_redirecting_to_ad_destination(self):
        _, advertisement = self.create_campaign("Click campaign")
        self.client.force_login(self.talent_user)
        token = create_tracking_token(advertisement.pk, self.talent_user.pk)

        response = self.client.get(
            f"{reverse('advertisement_click', args=(advertisement.pk,))}"
            f"?token={token}"
        )
        repeated_response = self.client.get(
            f"{reverse('advertisement_click', args=(advertisement.pk,))}"
            f"?token={token}"
        )

        self.assertRedirects(
            response,
            advertisement.destination_url,
            fetch_redirect_response=False,
        )
        self.assertEqual(repeated_response.status_code, 302)
        self.assertTrue(
            AdvertisementEvent.objects.filter(
                advertisement=advertisement,
                user=self.talent_user,
                event_type="CLICK",
            ).count(),
            1,
        )

    @override_settings(PAYSTACK_SECRET_KEY="test-secret")
    def test_paystack_webhook_rejects_invalid_signature(self):
        payload = json.dumps({"event": "charge.success", "data": {}}).encode()

        response = self.client.post(
            reverse("advertising_paystack_webhook"),
            data=payload,
            content_type="application/json",
            HTTP_X_PAYSTACK_SIGNATURE="invalid",
        )

        self.assertEqual(response.status_code, 401)

    @override_settings(PAYSTACK_SECRET_KEY="test-secret")
    @patch(
        "advertising.views._verified_transaction",
        return_value={"status": "success"},
    )
    def test_paystack_webhook_verifies_and_credits_payment_once(
        self,
        verify_payment,
    ):
        campaign, _ = self.create_campaign(
            "Pending payment campaign",
            status="APPROVED",
        )
        payment = CampaignPayment.objects.create(
            campaign=campaign,
            reference="paystack-ref",
            amount="25.00",
            currency=campaign.currency,
        )
        payload = json.dumps(
            {
                "event": "charge.success",
                "data": {"reference": payment.reference},
            }
        ).encode()
        signature = hmac.new(
            b"test-secret",
            payload,
            hashlib.sha512,
        ).hexdigest()

        response = self.client.post(
            reverse("advertising_paystack_webhook"),
            data=payload,
            content_type="application/json",
            HTTP_X_PAYSTACK_SIGNATURE=signature,
        )

        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, "SUCCESS")
        self.assertIsNotNone(payment.paid_at)
        verify_payment.assert_called_once()

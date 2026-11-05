from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from .models import Advertisement, AdvertisementEvent, Campaign, CampaignPayment
from .services import InvalidTrackingToken, create_tracking_token, get_ads_for_user, insert_ads_into_feed, record_ad_event
from organizations.models import Organization


class AdvertisingAgePrivacyTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username='advertiser', role='ORGANIZATION', date_of_birth=date(1990, 1, 1))
        organization = Organization.objects.create(user=owner, name='Advertiser')
        today = timezone.localdate()
        campaign = Campaign.objects.create(organization=organization, name='General', status='ACTIVE',
            start_date=today - timedelta(days=1), end_date=today + timedelta(days=2), total_budget='100.00')
        CampaignPayment.objects.create(campaign=campaign, reference='funded', amount='100.00', currency=campaign.currency, status='SUCCESS')
        self.ad = Advertisement.objects.create(campaign=campaign, title='General ad', destination_url='https://example.com/')
        self.user = User.objects.create_user(username='viewer', date_of_birth=date(1990, 1, 1))

    def test_minors_and_unknown_age_receive_no_ads_or_tracking_even_with_old_adult_token(self):
        token = create_tracking_token(self.ad.pk, self.user.pk)
        feed = [{'type': 'POST', 'object': 'ordinary content'}]
        for birth in [date(timezone.localdate().year - 10, 1, 1), date(timezone.localdate().year - 15, 1, 1), None]:
            with self.subTest(birth=birth):
                User.objects.filter(pk=self.user.pk).update(date_of_birth=birth)
                self.assertEqual(get_ads_for_user(self.user), [])
                self.assertEqual(insert_ads_into_feed(feed, [self.ad], self.user), feed)
                with self.assertRaises(InvalidTrackingToken):
                    create_tracking_token(self.ad.pk, self.user.pk)
                for event in ['IMPRESSION', 'CLICK', 'VIDEO_VIEW']:
                    with self.assertRaises(InvalidTrackingToken):
                        record_ad_event(self.ad.pk, self.user, event, token)
        self.assertFalse(AdvertisementEvent.objects.exists())

    def test_known_adult_delivery_and_idempotent_tracking_still_work(self):
        self.assertEqual(get_ads_for_user(self.user), [self.ad])
        items = insert_ads_into_feed([], [self.ad], self.user)
        self.assertEqual(items[0]['type'], 'ADVERTISEMENT')
        token = items[0]['tracking_token']
        self.assertTrue(record_ad_event(self.ad.pk, self.user, 'IMPRESSION', token))
        self.assertFalse(record_ad_event(self.ad.pk, self.user, 'IMPRESSION', token))

    def test_stale_adult_click_cannot_redirect_minor_to_advertiser(self):
        token = create_tracking_token(self.ad.pk, self.user.pk)
        self.client.force_login(self.user)
        User.objects.filter(pk=self.user.pk).update(date_of_birth=date(timezone.localdate().year - 15, 1, 1))
        response = self.client.get(reverse('advertisement_click', args=[self.ad.pk]), {'token': token})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(AdvertisementEvent.objects.exists())

    def test_inactive_adult_is_not_an_ad_recipient(self):
        token = create_tracking_token(self.ad.pk, self.user.pk)
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(get_ads_for_user(self.user), [])
        with self.assertRaises(InvalidTrackingToken):
            record_ad_event(self.ad.pk, self.user, 'IMPRESSION', token)

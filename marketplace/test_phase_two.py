from datetime import timedelta
from decimal import Decimal
from unittest import skipUnless
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection, IntegrityError, transaction
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import UserBlock
from organizations.models import OrganizationMembership
from notifications.models import Notification
from . import tests as fixtures
from .models import AvailabilityWindow, Booking, BookingEvent, BookingReview, DealMessage, Listing, Offer
from .services import booking_notification_is_current


@override_settings(**fixtures.MarketTests._overridden_settings, MARKETPLACE_BOOKINGS_ENABLED=True)
class PhaseTwoTests(APITestCase):
    setUpTestData = classmethod(fixtures.MarketTests.setUpTestData.__func__)
    base = '/api/marketplace/'

    def setUp(self):
        self.start = (timezone.now() + timedelta(days=2)).replace(microsecond=0)
        self.window = AvailabilityWindow.objects.create(talent=self.profile, starts_at=self.start - timedelta(hours=1), ends_at=self.start + timedelta(hours=8))
        self.auth(self.talent)
        response = self.client.patch(self.base + f'listings/{self.listing.pk}/',
            {'booking_enabled': True, 'pricing_mode': 'FIXED', 'base_price': '120.00', 'duration_minutes': 90, 'buffer_minutes': 15, 'consent': True}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.listing.refresh_from_db()

    def auth(self, user):
        self.client.force_authenticate(user)

    def propose(self, user=None, **overrides):
        self.auth(user or self.scout)
        data = {'listing': self.listing.pk, 'terms': 'Exact agreed service', 'starts_at': self.start.isoformat(), 'expected_revision': self.listing.revision}
        data.update(overrides)
        return self.client.post(self.base + 'offers/', data, format='json')

    def accept(self, offer_id):
        self.auth(self.talent)
        return self.client.post(self.base + f'deals/{offer_id}/', {'action': 'ACCEPT', 'consent': True}, format='json')

    def booking(self):
        offer = self.propose()
        self.assertEqual(offer.status_code, 201, offer.data)
        accepted = self.accept(offer.data['id'])
        self.assertEqual(accepted.status_code, 200, accepted.data)
        return Booking.objects.get(offer_id=offer.data['id'])

    def action(self, booking, user, action, **extra):
        self.auth(user)
        return self.client.post(self.base + f'bookings/{booking.pk}/', {'action': action, **extra}, format='json')

    def start_work(self, booking):
        with patch('django.utils.timezone.now', return_value=self.start):
            self.assertEqual(self.action(booking, self.talent, 'START').status_code, 200)

    def finish(self, booking):
        self.start_work(booking)
        self.auth(self.talent)
        response = self.client.post(self.base + f'bookings/{booking.pk}/submissions/', {'summary': 'Delivered service'}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.action(booking, self.scout, 'COMPLETE').status_code, 200)

    def test_legacy_offer_stays_unpriced_and_does_not_create_booking(self):
        legacy = Listing.objects.create(talent=self.profile, ecosystem='SPORTS', subecosystem=self.domain,
            title='Legacy', description='Preserved', status='PUBLISHED', publication_consented_at=timezone.now())
        self.auth(self.scout)
        offer = self.client.post(self.base + 'offers/', {'listing': legacy.pk, 'terms': 'Legacy terms'}, format='json')
        self.assertEqual(offer.status_code, 201)
        self.assertEqual(offer.data['workflow_version'], 1)
        self.assertIsNone(offer.data['quoted_amount'])
        self.assertEqual(self.accept(offer.data['id']).status_code, 200)
        self.assertFalse(Booking.objects.exists())

    def test_server_quote_and_immutable_snapshot_after_listing_changes(self):
        response = self.propose(quoted_amount='0.01', workflow_version=1, sender=self.outsider.pk)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['quoted_amount'], '120.00')
        self.assertEqual(response.data['workflow_version'], 2)
        self.assertEqual(response.data['sender'], self.scout.pk)
        self.auth(self.talent)
        self.client.patch(self.base + f'listings/{self.listing.pk}/', {'base_price': '999.00', 'description': 'Changed', 'consent': True}, format='json')
        accepted = self.accept(response.data['id'])
        self.assertEqual(accepted.status_code, 200, accepted.data)
        booking = Booking.objects.get(offer_id=response.data['id'])
        self.assertEqual(booking.amount, Decimal('120.00'))
        self.assertEqual(booking.snapshot['description'], 'Available for a team')
        self.assertEqual(booking.snapshot['terms'], 'Exact agreed service')
        self.assertEqual(booking.snapshot['collection'], 'NONE')
        self.assertEqual(booking.busy_start, self.start - timedelta(minutes=15))

    def test_hourly_and_negotiated_prices(self):
        Listing.objects.filter(pk=self.listing.pk).update(pricing_mode='HOURLY', base_price='10.01')
        response = self.propose()
        self.assertEqual(response.data['quoted_amount'], '15.02')
        self.auth(self.scout)
        self.client.post(self.base + f'deals/{response.data["id"]}/', {'action': 'WITHDRAW'}, format='json')
        Listing.objects.filter(pk=self.listing.pk).update(pricing_mode='QUOTE_ONLY', base_price=None)
        self.assertEqual(self.propose().status_code, 400)
        self.assertEqual(self.propose(negotiated_amount='82.50').data['quoted_amount'], '82.50')

    def test_invalid_quote_inputs_and_stale_revision(self):
        for data, status in [({'expected_revision': 999}, 409), ({'starts_at': self.start.replace(tzinfo=None).isoformat()}, 400),
                              ({'starts_at': '9999-12-31T23:59:00Z'}, 400), ({'negotiated_amount': '3.00'}, 400),
                              ({'starts_at': (self.start + timedelta(days=10)).isoformat()}, 409)]:
            with self.subTest(data=data):
                self.assertEqual(self.propose(**data).status_code, status)
        self.auth(self.scout)
        self.assertEqual(self.client.post(self.base + 'offers/', {'listing': self.listing.pk, 'terms': 'Old client'}, format='json').status_code, 400)
        self.assertFalse(Offer.objects.exists())

    def test_listing_price_permissions_and_validation(self):
        url = self.base + f'listings/{self.listing.pk}/'
        self.auth(self.scout)
        self.assertEqual(self.client.patch(url, {'base_price': '1.00', 'consent': True}, format='json').status_code, 403)
        self.auth(self.talent)
        for data in [{'base_price': '0'}, {'base_price': 'NaN'}, {'currency': 'XYZ'}, {'duration_minutes': 0}, {'duration_minutes': 1441}, {'buffer_minutes': 241}]:
            self.assertEqual(self.client.patch(url, {**data, 'consent': True}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(url, {'base_price': '200'}, format='json').status_code, 400)
        with override_settings(MARKETPLACE_CURRENCY='USD'):
            new_listing = self.client.post(self.base + 'listings/', {'title': 'New currency', 'description': 'Unpriced legacy-style creation',
                'ecosystem': 'SPORTS', 'subecosystem': self.domain.pk}, format='json')
            self.assertEqual(new_listing.status_code, 201, new_listing.data)
            self.assertEqual(new_listing.data['currency'], 'USD')

    def test_rollout_flag_preserves_existing_booking_operations(self):
        booking = self.booking()
        pending = self.propose(self.coach, starts_at=(self.start + timedelta(hours=4)).isoformat())
        self.assertEqual(pending.status_code, 201)
        with override_settings(MARKETPLACE_BOOKINGS_ENABLED=False):
            self.assertEqual(self.accept(pending.data['id']).status_code, 409)
            self.assertEqual(Offer.objects.get(pk=pending.data['id']).status, 'PENDING')
            self.assertEqual(self.propose(starts_at=(self.start + timedelta(hours=6)).isoformat()).status_code, 409)
            self.auth(self.scout)
            self.assertEqual(self.client.get(self.base + f'bookings/{booking.pk}/').status_code, 200)
            self.assertEqual(self.client.post(self.base + f'bookings/{booking.pk}/messages/', {'body': 'Existing fulfillment'}, format='json').status_code, 201)

    def test_availability_validation_owner_and_reservation_protection(self):
        self.auth(self.talent)
        for data in [dict(starts_at=self.start.isoformat(), ends_at=self.start.isoformat()),
                     dict(starts_at=(self.start + timedelta(days=10)).isoformat(), ends_at=(self.start + timedelta(days=10, hours=2)).isoformat(), timezone='Invalid/Zone')]:
            self.assertEqual(self.client.post(self.base + 'availability/', data, format='json').status_code, 400)
        self.assertEqual(self.client.post(self.base + 'availability/', {'starts_at': self.start.isoformat(), 'ends_at': (self.start + timedelta(hours=1)).isoformat()}, format='json').status_code, 409)
        booking = self.booking()
        self.auth(self.talent)
        self.assertEqual(self.client.delete(self.base + f'availability/{self.window.pk}/').status_code, 409)
        self.auth(self.coach)
        self.assertIn(self.client.delete(self.base + f'availability/{self.window.pk}/').status_code, [404])
        free = self.client.get(self.base + f'availability/?listing={self.listing.pk}')
        self.assertEqual(free.status_code, 200)
        self.assertNotIn('offer', str(free.data))
        self.assertNotIn('sender', str(free.data))
        self.auth(self.talent)
        self.assertEqual(self.client.get(self.base + 'availability/?listing=bad').status_code, 400)

    def test_overlap_rolls_back_acceptance_and_cancel_releases_slot(self):
        first = self.propose()
        second = self.propose(self.coach)
        self.assertEqual(self.accept(first.data['id']).status_code, 200)
        response = self.accept(second.data['id'])
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(Offer.objects.get(pk=second.data['id']).status, 'PENDING')
        booking = Booking.objects.get(offer_id=first.data['id'])
        self.assertEqual(self.action(booking, self.scout, 'CANCEL', reason='Unavailable').status_code, 200)
        self.assertEqual(self.accept(second.data['id']).status_code, 200)
        self.assertEqual(Offer.objects.get(pk=first.data['id']).status, 'ACCEPTED')

    def test_booking_access_and_revoked_organization_sender(self):
        offer = self.propose(organization=self.org.pk)
        self.assertEqual(self.accept(offer.data['id']).status_code, 200)
        booking = Booking.objects.get(offer_id=offer.data['id'])
        url = self.base + f'bookings/{booking.pk}/'
        for user in [self.outsider, self.coach]:
            self.auth(user)
            for suffix in ['', 'messages/', 'submissions/', 'events/']:
                self.assertEqual(self.client.get(url + suffix).status_code, 403)
            self.assertEqual(self.client.post(url + 'reviews/', {'rating': 5, 'text': 'Intrusion'}, format='json').status_code, 403)
            self.assertEqual(self.client.get(self.base + 'bookings/').data['count'], 0)
        OrganizationMembership.objects.filter(pk=self.member.pk).update(status='SUSPENDED')
        self.auth(self.scout)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.get(self.base + 'bookings/').data['count'], 0)
        self.auth(self.talent)
        self.assertEqual(self.client.get(url).status_code, 200)
        notification = Notification.objects.filter(user=self.scout).first()
        self.assertIsNotNone(notification)
        self.assertFalse(booking_notification_is_current(notification))
        UserBlock.objects.create(user=self.scout, blocked_user=self.talent)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_message_scopes_are_separate_and_terminal_bookings_read_only(self):
        booking = self.booking()
        self.auth(self.scout)
        url = self.base + f'bookings/{booking.pk}/messages/'
        response = self.client.post(url, {'body': 'Fulfillment message', 'author': self.outsider.pk, 'scope': 'NEGOTIATION'}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['author'], self.scout.pk)
        self.assertEqual(DealMessage.objects.get(pk=response.data['id']).scope, 'FULFILLMENT')
        old_url = self.base + f'deals/{booking.offer_id}/messages/'
        self.assertEqual(self.client.get(old_url).data['messages'], [])
        self.assertEqual(self.client.post(old_url, {'body': 'After acceptance'}, format='json').status_code, 400)
        self.assertEqual(self.action(booking, self.talent, 'CANCEL', reason='Cancelled before start').status_code, 200)
        self.auth(self.scout)
        self.assertEqual(self.client.post(url, {'body': 'Too late'}, format='json').status_code, 400)
        self.assertEqual(len(self.client.get(url).data['messages']), 1)

    def test_fulfillment_versions_completion_and_private_artifact(self):
        booking = self.booking()
        self.assertEqual(self.action(booking, self.talent, 'START').status_code, 403)
        self.start_work(booking)
        self.auth(self.scout)
        url = self.base + f'bookings/{booking.pk}/submissions/'
        self.assertEqual(self.client.post(url, {'summary': 'Forged'}, format='json').status_code, 403)
        self.auth(self.talent)
        sent = self.client.post(url, {'summary': '<script>Delivery</script>', 'artifact': SimpleUploadedFile('private.txt', b'Private delivery')}, format='multipart')
        self.assertEqual(sent.status_code, 201, sent.data)
        self.assertEqual(self.action(booking, self.talent, 'COMPLETE').status_code, 403)
        download = url + f'{sent.data["id"]}/artifact/'
        self.auth(self.scout)
        response = self.client.get(download)
        self.assertEqual(b''.join(response.streaming_content), b'Private delivery')
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        encoded = self.client.get(download + '?encoding=base64')
        self.assertEqual(encoded.data['content'], 'UHJpdmF0ZSBkZWxpdmVyeQ==')
        self.auth(self.outsider)
        self.assertEqual(self.client.get(download).status_code, 403)
        self.assertEqual(self.action(booking, self.scout, 'REQUEST_CHANGES').status_code, 400)
        self.assertEqual(self.action(booking, self.scout, 'REQUEST_CHANGES', reason='Please revise').status_code, 200)
        self.auth(self.talent)
        self.assertEqual(self.client.get(self.base + f'bookings/{booking.pk}/events/').data['results'][0]['reason'], 'Please revise')
        self.assertEqual(self.client.post(url, {'summary': 'Second version'}, format='json').data['sequence'], 2)
        self.assertEqual(self.action(booking, self.scout, 'COMPLETE').status_code, 200)
        self.assertEqual(self.action(booking, self.talent, 'CANCEL', reason='After work').status_code, 403)
        self.assertEqual(booking.submissions.count(), 2)
        self.assertEqual(booking.submissions.first().summary, '<script>Delivery</script>')

    def test_completed_review_consent_uniqueness_visibility_and_moderation(self):
        booking = self.booking()
        url = self.base + f'bookings/{booking.pk}/reviews/'
        self.auth(self.scout)
        self.assertEqual(self.client.post(url, {'rating': 5, 'text': 'Too soon'}, format='json').status_code, 403)
        self.finish(booking)
        self.auth(self.talent)
        self.assertEqual(self.client.post(url, {'rating': 5, 'text': 'Self-review'}, format='json').status_code, 403)
        self.auth(self.scout)
        self.assertEqual(self.client.post(url, {'rating': 6, 'text': 'Invalid'}, format='json').status_code, 400)
        self.assertEqual(self.client.post(url, {'rating': 2, 'text': 'Verified feedback', 'publish': True}, format='json').status_code, 201)
        self.assertEqual(self.client.post(url, {'rating': 5, 'text': 'Duplicate'}, format='json').status_code, 403)
        self.auth(self.coach)
        public = self.base + f'listings/{self.listing.pk}/reviews/'
        response = self.client.get(public)
        self.assertEqual(response.data['average'], 2)
        self.assertEqual(set(response.data['results'][0]), {'rating', 'text', 'reviewer'})
        self.auth(self.talent)
        self.assertEqual(self.client.patch(url, {'publish': False}, format='json').status_code, 403)
        self.auth(self.scout)
        self.assertEqual(self.client.patch(url, {'publish': False}, format='json').status_code, 200)
        self.auth(self.coach)
        self.assertEqual(self.client.get(public).data['count'], 0)
        self.auth(self.scout)
        self.assertEqual(self.client.patch(url, {'publish': True}, format='json').status_code, 200)
        self.auth(self.coach)
        review = BookingReview.objects.get(booking=booking)
        BookingReview.objects.filter(pk=review.pk).update(publication_consented_at=None)
        self.assertEqual(self.client.get(public).data['count'], 0)
        BookingReview.objects.filter(pk=review.pk).update(publication_consented_at=timezone.now(), moderation_state='HIDDEN')
        self.assertEqual(self.client.get(public).data['count'], 0)
        self.profile.profile_visibility = 'PRIVATE'; self.profile.save()
        self.assertEqual(self.client.get(public).status_code, 404)

    @skipUnless(connection.vendor == 'postgresql', 'PostgreSQL exclusion and numeric guards')
    def test_database_rejects_overlap_missing_quote_end_and_nan(self):
        booking = self.booking()
        other = Offer.objects.create(listing=self.listing, sender=self.coach, terms='Other legacy offer')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Booking.objects.create(offer=other, talent=self.profile, starts_at=booking.starts_at, ends_at=booking.ends_at,
                busy_start=booking.busy_start, busy_end=booking.busy_end, amount='5.00', currency='GHS')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Offer.objects.filter(pk=booking.offer_id).update(requested_end=None)
        for table, column, pk in [('marketplace_offer', 'quoted_amount', booking.offer_id), ('marketplace_booking', 'amount', booking.pk)]:
            with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
                # Bypass Django's own NaN rejection to test the database guard itself.
                from psycopg2 import sql
                cursor.execute(sql.SQL('UPDATE {} SET {} = %s::numeric WHERE id = %s').format(sql.Identifier(table), sql.Identifier(column)), ['NaN', pk])

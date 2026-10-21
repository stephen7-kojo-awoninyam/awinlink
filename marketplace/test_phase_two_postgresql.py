from datetime import timedelta
from unittest import skipUnless

from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from . import tests as fixtures
from .models import AvailabilityWindow, Booking, BookingEvent, Listing, Offer
from .services import quote
from .test_postgresql import ConcurrentMarketTests as RaceHelpers


@skipUnless(connection.vendor == 'postgresql', 'PostgreSQL provider locking and exclusion constraints')
@override_settings(**fixtures.MarketTests._overridden_settings, MARKETPLACE_BOOKINGS_ENABLED=True)
class PhaseTwoConcurrencyTests(TransactionTestCase):
    setUpTestData = classmethod(fixtures.MarketTests.setUpTestData.__func__)
    race = RaceHelpers.race
    post = RaceHelpers.post

    def setUp(self):
        self.setUpTestData()
        self.start = timezone.now() + timedelta(days=2)
        AvailabilityWindow.objects.create(talent=self.profile, starts_at=self.start - timedelta(hours=1), ends_at=self.start + timedelta(hours=8))
        Listing.objects.filter(pk=self.listing.pk).update(booking_enabled=True, pricing_mode='FIXED', base_price='40.00', buffer_minutes=15)
        self.listing.refresh_from_db()

    def proposal(self, listing, user, start=None):
        snapshot = quote(listing, {'starts_at': start or self.start, 'expected_revision': listing.revision})
        return Offer.objects.create(listing=listing, sender=user, terms='Concurrent exact terms', **snapshot)

    def accept(self, offer):
        return self.post(self.talent.pk, f'deals/{offer.pk}/', {'action': 'ACCEPT', 'consent': True})

    def test_same_talent_different_listings_cannot_double_book(self):
        second_listing = Listing.objects.create(talent=self.profile, ecosystem='SPORTS', subecosystem=self.domain,
            title='Another service', description='Same provider', status='PUBLISHED', publication_consented_at=timezone.now(),
            booking_enabled=True, pricing_mode='FIXED', base_price='50.00', buffer_minutes=15)
        first, second = self.proposal(self.listing, self.scout), self.proposal(second_listing, self.coach)
        self.assertEqual(sorted(self.race(lambda: self.accept(first), lambda: self.accept(second))), [200, 409])
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(BookingEvent.objects.count(), 1)
        self.assertEqual(Offer.objects.filter(status='PENDING', talent_consented_at__isnull=True, decided_at__isnull=True).count(), 1)

    def test_duplicate_acceptance_creates_one_booking_and_event(self):
        offer = self.proposal(self.listing, self.scout)
        self.assertEqual(sorted(self.race(lambda: self.accept(offer), lambda: self.accept(offer))), [200, 400])
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(BookingEvent.objects.count(), 1)

    def test_adjacent_buffered_intervals_both_succeed(self):
        first = self.proposal(self.listing, self.scout)
        second = self.proposal(self.listing, self.coach, self.start + timedelta(minutes=90))
        self.assertEqual(self.race(lambda: self.accept(first), lambda: self.accept(second)), [200, 200])
        bookings = list(Booking.objects.order_by('starts_at'))
        self.assertEqual(bookings[0].busy_end, bookings[1].busy_start)

    def test_cancel_racing_acceptance_never_leaves_overlapping_reservations(self):
        original = self.proposal(self.listing, self.scout)
        replacement = self.proposal(self.listing, self.coach)
        self.assertEqual(self.accept(original), 200)
        booking = Booking.objects.get(offer=original)
        cancelled, accepted = self.race(
            lambda: self.post(self.scout.pk, f'bookings/{booking.pk}/', {'action': 'CANCEL', 'reason': 'Release time'}),
            lambda: self.accept(replacement))
        self.assertEqual(cancelled, 200)
        self.assertIn(accepted, [200, 409])
        if accepted == 409:
            self.assertEqual(self.accept(replacement), 200)
        self.assertEqual(Booking.objects.exclude(status='CANCELLED').count(), 1)

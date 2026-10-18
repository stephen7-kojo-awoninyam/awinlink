"""Transaction and partial-index regressions requiring PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from accounts.models import User
from organizations.models import OrganizationMembership
from .models import Offer
from . import tests as fixtures


@skipUnless(connection.vendor == 'postgresql', 'PostgreSQL row locks required')
class ConcurrentMarketTests(TransactionTestCase):
    # Reuse fixtures, without inheriting the API test methods.
    setUpTestData = classmethod(fixtures.MarketTests.setUpTestData.__func__)

    def setUp(self):
        self.setUpTestData()
        self.settings_override = fixtures.MarketTests._overridden_settings
        from django.test import override_settings
        override = override_settings(**self.settings_override)
        override.enable()
        self.addCleanup(override.disable)

    def race(self, *operations):
        barrier = Barrier(len(operations))

        def run(operation):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '8s'")
                    cursor.execute("SET statement_timeout = '15s'")
                barrier.wait(timeout=10)
                return operation()
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=len(operations)) as pool:
            futures = [pool.submit(run, operation) for operation in operations]
            return [future.result(timeout=25) for future in futures]

    def post(self, user_id, path, data):
        client = APIClient()
        client.force_authenticate(User.objects.get(pk=user_id))
        return client.post('/api/marketplace/' + path, data, format='json').status_code

    def test_concurrent_personal_offer_retries(self):
        def send():
            return self.post(self.scout.pk, 'offers/', {'listing': self.listing.pk, 'terms': 'Terms'})
        self.assertEqual(sorted(self.race(send, send)), [201, 400])
        self.assertEqual(Offer.objects.count(), 1)

    def test_concurrent_organization_recruiters(self):
        OrganizationMembership.objects.create(organization=self.org, user=self.coach, role='RECRUITER')
        def send(user):
            return self.post(user.pk, 'offers/', {'listing': self.listing.pk, 'organization': self.org.pk, 'terms': 'Terms'})
        self.assertEqual(sorted(self.race(lambda: send(self.scout), lambda: send(self.coach))), [201, 400])
        self.assertEqual(Offer.objects.count(), 1)

    def test_competing_final_decisions(self):
        offer = Offer.objects.create(listing=self.listing, sender=self.scout, terms='Terms')
        path = f'deals/{offer.pk}/'
        outcomes = self.race(
            lambda: self.post(self.talent.pk, path, {'action': 'ACCEPT', 'consent': True}),
            lambda: self.post(self.scout.pk, path, {'action': 'WITHDRAW'}),
        )
        self.assertEqual(sorted(outcomes), [200, 400])
        offer.refresh_from_db()
        self.assertIn(offer.status, ['ACCEPTED', 'WITHDRAWN'])
        self.assertEqual(offer.talent_consented_at is not None, offer.status == 'ACCEPTED')

    def test_message_racing_final_decision(self):
        offer = Offer.objects.create(listing=self.listing, sender=self.scout, terms='Terms')
        path = f'deals/{offer.pk}/'
        outcomes = self.race(
            lambda: self.post(self.scout.pk, path + 'messages/', {'body': 'Before final decision'}),
            lambda: self.post(self.talent.pk, path, {'action': 'DECLINE'}),
        )
        self.assertIn(outcomes[0], [201, 400])
        self.assertEqual(outcomes[1], 200)
        self.assertEqual(self.post(self.scout.pk, path + 'messages/', {'body': 'Too late'}), 400)
        self.assertEqual(offer.messages.count(), int(outcomes[0] == 201))

from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from django.db import connection, close_old_connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase, override_settings

from . import tests as fixtures, test_postgresql as races, test_payments as payments
from .models import Booking, Offer, Listing, MarketInvoice, MarketRefund, MarketTransaction


@skipUnless(connection.vendor == 'postgresql', 'Payment record row locking requires PostgreSQL')
@override_settings(**fixtures.MarketTests._overridden_settings, MARKETPLACE_PLATFORM_FEE_BPS=250)
class PaymentConcurrencyTests(TransactionTestCase):
    setUpTestData = classmethod(fixtures.MarketTests.setUpTestData.__func__)
    race = races.ConcurrentMarketTests.race
    post = races.ConcurrentMarketTests.post

    def setUp(self):
        self.setUpTestData()
        payments.PaymentTests.setUp(self)
        self.path = f'bookings/{self.booking.pk}/invoice/'

    def issue(self):
        self.assertEqual(self.post(self.talent.pk, self.path, {}), 201)

    def request(self, amount='120.00', key=None):
        return self.post(self.scout.pk, self.path+'refunds/', {
            'amount': amount, 'reason': 'Adjustment', 'idempotency_key': str(key or uuid4())})

    def decide(self, refund, action='APPROVE'):
        return self.post(self.talent.pk, self.path+f'refunds/{refund.pk}/', {'action': action, 'reason': 'Reviewed'})

    def test_duplicate_issue_records_one_invoice_and_transaction(self):
        operation = lambda: self.post(self.talent.pk, self.path, {})
        self.assertEqual(sorted(self.race(operation, operation)), [200, 201])
        self.assertEqual(MarketInvoice.objects.count(), 1)
        self.assertEqual(MarketTransaction.objects.count(), 1)

    def test_duplicate_refund_request_key_is_idempotent_under_concurrency(self):
        self.issue(); key = uuid4()
        operation = lambda: self.request(key=key)
        self.assertEqual(sorted(self.race(operation, operation)), [200, 201])
        self.assertEqual(MarketRefund.objects.count(), 1)

    def test_competing_refunds_cannot_overreserve_balance(self):
        self.issue()
        self.assertEqual(sorted(self.race(self.request, self.request)), [201, 409])
        self.assertEqual(MarketRefund.objects.count(), 1)

    def test_duplicate_approval_credits_once(self):
        self.issue(); self.assertEqual(self.request(), 201)
        refund = MarketRefund.objects.get()
        self.assertEqual(self.race(lambda: self.decide(refund), lambda: self.decide(refund)), [200, 200])
        invoice = MarketInvoice.objects.get()
        self.assertEqual((invoice.status, invoice.credited_amount, invoice.credited_fee), ('CREDITED', 120, 3))
        self.assertEqual(MarketTransaction.objects.filter(kind='REFUND_APPROVED').count(), 1)

    def test_approval_and_rejection_have_one_final_winner(self):
        self.issue(); self.assertEqual(self.request(), 201)
        refund = MarketRefund.objects.get()
        self.assertEqual(sorted(self.race(lambda: self.decide(refund), lambda: self.decide(refund, 'REJECT'))), [200, 409])
        refund.refresh_from_db(); invoice = MarketInvoice.objects.get()
        approved = refund.status == 'APPROVED'
        self.assertEqual(invoice.credited_amount, 120 if approved else 0)
        self.assertEqual(MarketTransaction.objects.filter(kind='REFUND_APPROVED').count(), int(approved))

    def test_membership_revocation_serializes_against_refund_creation(self):
        from accounts.models import User
        from organizations.models import OrganizationMembership
        from organizations.services import suspend_team_member
        self.booking.offer.organization = self.org
        self.booking.offer.save(update_fields=['organization'])
        OrganizationMembership.objects.create(organization=self.org, user=self.outsider, role='OWNER')
        self.issue()
        def revoke():
            suspend_team_member(organization=self.org, actor=User.objects.get(pk=self.outsider.pk), membership=self.member.pk)
            return 200
        revoked, requested = self.race(revoke, self.request)
        self.assertEqual(revoked, 200)
        self.assertIn(requested, [201, 403])
        self.assertEqual(MarketRefund.objects.count(), int(requested == 201))

    def assert_safety_change_waits_for_credit(self, change):
        from . import payment_services
        self.issue(); self.assertEqual(self.request(), 201)
        refund = MarketRefund.objects.get()
        ready, release, started, finished = [Event() for _ in range(4)]
        original = payment_services.record
        def pause(*args, **kwargs):
            row = original(*args, **kwargs)
            ready.set()
            if not release.wait(timeout=15):
                raise RuntimeError('Credit test release timed out')
            return row
        def credit():
            close_old_connections()
            try:
                return self.decide(refund)
            finally:
                connection.close()
        def safety():
            close_old_connections(); started.set()
            try:
                change(); finished.set()
            finally:
                connection.close()
        with patch('marketplace.payment_services.record', side_effect=pause), ThreadPoolExecutor(max_workers=2) as pool:
            decision = pool.submit(credit)
            try:
                self.assertTrue(ready.wait(timeout=15))
                changed = pool.submit(safety)
                self.assertTrue(started.wait(timeout=15))
                self.assertFalse(finished.wait(timeout=0.5))
            finally:
                release.set()
            self.assertEqual(decision.result(timeout=15), 200)
            changed.result(timeout=15)
        self.assertTrue(finished.is_set())
        self.assertEqual(MarketTransaction.objects.filter(kind='REFUND_APPROVED').count(), 1)

    def test_account_suspension_cannot_commit_inside_the_checked_credit(self):
        from accounts.models import User
        self.assert_safety_change_waits_for_credit(lambda: User.objects.filter(pk=self.scout.pk).update(is_active=False))

    def test_block_cannot_commit_inside_the_checked_credit(self):
        from accounts.models import UserBlock
        self.assert_safety_change_waits_for_credit(lambda: UserBlock.objects.create(user=self.scout, blocked_user=self.talent))

    def test_busy_account_returns_conflict_without_creating_refund(self):
        from accounts.models import User
        self.issue(); ready, release = Event(), Event()
        def hold():
            close_old_connections()
            try:
                with transaction.atomic():
                    User.objects.select_for_update().get(pk=self.scout.pk)
                    ready.set()
                    if not release.wait(timeout=15):
                        raise RuntimeError('Account test release timed out')
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=1) as pool:
            holder = pool.submit(hold)
            try:
                self.assertTrue(ready.wait(timeout=15))
                self.assertEqual(self.request(), 409)
            finally:
                release.set()
            holder.result(timeout=15)
        self.assertFalse(MarketRefund.objects.exists())
        self.assertEqual(self.request(), 201)

    def test_payment_schema_preserves_existing_bookings_and_does_not_backfill_money(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(latest))
        models = [Booking, Offer, Listing]
        before = [list(model.objects.order_by('pk').values()) for model in models]
        executor.migrate([('marketplace', '0004_booking_overlap')])
        self.assertEqual([list(model.objects.order_by('pk').values()) for model in models], before)
        MigrationExecutor(connection).migrate(latest)
        self.assertEqual([list(model.objects.order_by('pk').values()) for model in models], before)
        self.assertFalse(MarketInvoice.objects.exists())
        self.assertFalse(MarketRefund.objects.exists())
        self.assertFalse(MarketTransaction.objects.exists())

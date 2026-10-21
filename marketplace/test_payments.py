from datetime import timedelta
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient

from accounts.models import UserBlock
from . import tests as fixtures, payment_services as services
from .models import Booking, Offer, MarketInvoice, MarketRefund, MarketTransaction


@override_settings(**fixtures.MarketTests._overridden_settings, MARKETPLACE_PLATFORM_FEE_BPS=250)
class PaymentTests(APITestCase):
    setUpTestData = classmethod(fixtures.MarketTests.setUpTestData.__func__)

    def setUp(self):
        now = timezone.now()
        offer = Offer.objects.create(listing=self.listing, sender=self.scout, terms='Agreed terms',
            status='ACCEPTED', talent_consented_at=now, decided_at=now)
        self.booking = Booking.objects.create(offer=offer, talent=self.profile, starts_at=now+timedelta(days=1),
            ends_at=now+timedelta(days=1, hours=1), busy_start=now+timedelta(days=1),
            busy_end=now+timedelta(days=1, hours=1), amount='120.00', currency='GHS', snapshot={'terms': 'Agreed terms'})
        self.url = f'/api/marketplace/bookings/{self.booking.pk}/invoice/'

    def post(self, suffix='', user=None, **data):
        self.client.force_authenticate(user or self.talent)
        return self.client.post(self.url+suffix, data, format='json')

    def issue(self):
        result = self.post()
        self.assertEqual(result.status_code, 201, result.data)
        return result.data

    def refund(self, amount='40.00', key=None):
        result = self.post('refunds/', self.scout, amount=amount, reason='Service adjustment', idempotency_key=str(key or uuid4()))
        self.assertEqual(result.status_code, 201, result.data)
        return result.data

    def decide(self, refund, action='APPROVE', **extra):
        return self.post(f"refunds/{refund['id']}/", action=action, reason='Reviewed adjustment', **extra)

    def test_invoice_uses_booking_snapshot_and_server_fee_without_collection(self):
        row = self.issue()
        self.assertEqual((row['amount'], row['fee_amount'], row['talent_amount']), ('120.00', '3.00', '117.00'))
        self.assertEqual((row['mode'], row['collection'], row['remaining_amount']), ('RECORD_ONLY', 'NONE', '120.00'))
        self.assertEqual(self.post().status_code, 200)
        with override_settings(MARKETPLACE_PLATFORM_FEE_BPS=9999):
            self.assertEqual(self.post().data['fee_bps'], 250)
        self.assertEqual(MarketInvoice.objects.count(), 1)
        record = MarketTransaction.objects.get()
        self.assertEqual((record.kind, record.amount, record.currency), ('INVOICE_ISSUED', Decimal('120'), 'GHS'))
        self.booking.refresh_from_db(); self.assertEqual(self.booking.status, 'CONFIRMED')

    def test_partial_and_full_refund_credits_do_not_move_money_or_cancel_booking(self):
        self.issue()
        for amount, status in [('40.00', 'PARTIALLY_CREDITED'), ('80.00', 'CREDITED')]:
            refund = self.refund(amount)
            self.assertEqual(self.decide(refund).status_code, 200)
            invoice = MarketInvoice.objects.get()
            self.assertEqual(invoice.status, status)
        self.assertEqual((invoice.credited_amount, invoice.credited_fee), (Decimal('120'), Decimal('3')))
        rows = MarketTransaction.objects.filter(kind='REFUND_APPROVED')
        self.assertEqual(sum(r.amount for r in rows), Decimal('120'))
        self.assertEqual(sum(r.fee_amount for r in rows), Decimal('3'))
        self.booking.refresh_from_db(); self.assertEqual(self.booking.status, 'CONFIRMED')

    def test_fee_rounding_is_cumulative_across_penny_refunds(self):
        Booking.objects.filter(pk=self.booking.pk).update(amount='0.05')
        with override_settings(MARKETPLACE_PLATFORM_FEE_BPS=3333):
            self.assertEqual(self.issue()['fee_amount'], '0.02')
        for _ in range(5):
            self.assertEqual(self.decide(self.refund('0.01')).status_code, 200)
        invoice = MarketInvoice.objects.get()
        self.assertEqual((invoice.credited_amount, invoice.credited_fee, invoice.status), (Decimal('.05'), Decimal('.02'), 'CREDITED'))
        self.assertEqual(sum(r.fee_amount for r in invoice.transactions.filter(kind='REFUND_APPROVED')), Decimal('.02'))

    def test_fractional_invoice_totals_balance_at_currency_precision(self):
        Booking.objects.filter(pk=self.booking.pk).update(amount='0.30')
        with override_settings(MARKETPLACE_PLATFORM_FEE_BPS=3333):
            row = self.issue()
        self.assertEqual((row['amount'], row['fee_amount'], row['talent_amount']), ('0.30', '0.10', '0.20'))

    def test_zero_fee_policy(self):
        with override_settings(MARKETPLACE_PLATFORM_FEE_BPS=0):
            self.assertEqual(self.issue()['fee_amount'], '0.00')
        self.assertEqual(self.decide(self.refund('120.00')).status_code, 200)

    def test_full_fee_policy(self):
        with override_settings(MARKETPLACE_PLATFORM_FEE_BPS=10000):
            row = self.issue()
        self.assertEqual((row['fee_amount'], row['talent_amount']), ('120.00', '0.00'))
        self.assertEqual(self.decide(self.refund('120.00')).status_code, 200)
        self.assertEqual(MarketInvoice.objects.get().credited_fee, Decimal('120.00'))

    def test_refund_idempotency_and_immutable_decisions(self):
        self.issue(); key = str(uuid4()); refund = self.refund(key=key)
        retry = self.post('refunds/', self.scout, amount='40.00', reason='Service adjustment', idempotency_key=key)
        self.assertEqual((retry.status_code, retry.data['id']), (200, refund['id']))
        self.assertEqual(self.post('refunds/', self.scout, amount='41.00', reason='Service adjustment', idempotency_key=key).status_code, 409)
        self.assertEqual(self.decide(refund).status_code, 200)
        self.assertEqual(self.decide(refund).status_code, 200)
        self.assertEqual(self.decide(refund, 'REJECT').status_code, 409)
        self.assertEqual(MarketRefund.objects.count(), 1)
        self.assertEqual(MarketTransaction.objects.filter(kind='REFUND_APPROVED').count(), 1)

    def test_pending_refunds_reserve_balance_and_rejection_releases_it(self):
        self.issue(); refund = self.refund('100.00')
        self.assertEqual(self.post('refunds/', self.scout, amount='21.00', reason='Too much', idempotency_key=str(uuid4())).status_code, 409)
        self.assertEqual(self.decide(refund, 'REJECT').status_code, 200)
        self.assertEqual(self.decide(self.refund('120.00')).status_code, 200)
        self.assertEqual(MarketTransaction.objects.filter(kind='REFUND_APPROVED').count(), 1)

    def test_void_is_a_recorded_reversal_and_cannot_be_edited_or_reissued(self):
        self.issue(); self.client.force_authenticate(self.talent)
        result = self.client.patch(self.url, {'action': 'VOID', 'reason': 'Issued in error'}, format='json')
        self.assertEqual((result.status_code, result.data['status'], result.data['remaining_amount']), (200, 'VOID', '0.00'))
        self.assertEqual(self.post().data['status'], 'VOID')
        self.assertEqual(self.post('refunds/', self.scout, amount='1', reason='No', idempotency_key=str(uuid4())).status_code, 409)
        self.assertEqual(MarketTransaction.objects.count(), 2)
        self.client.force_authenticate(self.talent)
        self.assertEqual(self.client.delete(self.url).status_code, 405)

    def test_pending_or_credited_invoice_cannot_be_voided(self):
        self.issue(); refund = self.refund()
        self.client.force_authenticate(self.talent)
        self.assertEqual(self.client.patch(self.url, {'action': 'VOID', 'reason': 'No'}, format='json').status_code, 409)
        self.decide(refund)
        self.assertEqual(self.client.patch(self.url, {'action': 'VOID', 'reason': 'No'}, format='json').status_code, 409)

    def test_refund_identifier_is_scoped_to_its_invoice(self):
        self.issue()
        now = timezone.now()
        offer = Offer.objects.create(listing=self.listing, sender=self.scout, terms='Other agreement',
            status='ACCEPTED', talent_consented_at=now, decided_at=now)
        other = Booking.objects.create(offer=offer, talent=self.profile, starts_at=now+timedelta(days=3),
            ends_at=now+timedelta(days=3, hours=1), busy_start=now+timedelta(days=3),
            busy_end=now+timedelta(days=3, hours=1), amount='20.00', currency='GHS')
        services.issue(other.pk, self.talent)
        refund, _ = services.request_refund(other.pk, self.scout, '10.00', 'Other invoice', uuid4())
        result = self.post(f'refunds/{refund.pk}/', action='APPROVE', reason='Wrong invoice')
        self.assertEqual(result.status_code, 404)
        refund.refresh_from_db(); self.assertEqual(refund.status, 'PENDING')
        self.assertFalse(MarketTransaction.objects.filter(kind='REFUND_APPROVED').exists())

    def test_void_record_failure_rolls_back_the_state_change(self):
        self.issue(); self.client.force_authenticate(self.talent)
        with patch('marketplace.payment_services.record', side_effect=RuntimeError('Injected void failure')):
            with self.assertRaises(RuntimeError):
                self.client.patch(self.url, {'action': 'VOID', 'reason': 'Issued in error'}, format='json')
        self.assertEqual(MarketInvoice.objects.get().status, 'ISSUED')
        self.assertEqual(MarketTransaction.objects.count(), 1)

    def test_financial_permissions_and_private_history(self):
        self.assertEqual(self.post(user=self.scout).status_code, 403)
        self.issue()
        self.assertEqual(self.post('refunds/', self.talent, amount='1', reason='No', idempotency_key=str(uuid4())).status_code, 403)
        refund = self.refund()
        self.assertEqual(self.decide(refund, user=self.scout).status_code, 403)
        for user in [self.outsider, self.coach]:
            self.client.force_authenticate(user)
            for suffix in ['', 'refunds/', 'transactions/']:
                self.assertEqual(self.client.get(self.url+suffix).status_code, 403)
        for user in [self.talent, self.scout]:
            self.client.force_authenticate(user)
            for suffix in ['', 'refunds/', 'transactions/']:
                result = self.client.get(self.url+suffix)
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result['Cache-Control'], 'private, no-store')
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_blocked_and_revoked_buyers_lose_financial_access(self):
        self.issue(); self.booking.offer.organization = self.org; self.booking.offer.save(update_fields=['organization'])
        self.member.status = 'SUSPENDED'; self.member.save(update_fields=['status'])
        self.assertEqual(self.post('refunds/', self.scout, amount='1', reason='No', idempotency_key=str(uuid4())).status_code, 403)
        UserBlock.objects.create(user=self.talent, blocked_user=self.scout)
        self.client.force_authenticate(self.talent)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_invalid_amounts_unknown_fields_and_provider_payloads_are_rejected(self):
        self.assertEqual(self.post(amount='0.01').status_code, 400)
        self.issue()
        for amount in ['0', '-1', 'NaN', 'Infinity', '1.001', '10000000000.00']:
            self.assertEqual(self.post('refunds/', self.scout, amount=amount, reason='No', idempotency_key=str(uuid4())).status_code, 400)
        self.assertEqual(self.post('refunds/', self.scout, amount='1', reason='No', idempotency_key=str(uuid4()), status='APPROVED').status_code, 400)
        self.assertEqual(self.post(provider_token='secret').status_code, 400)
        self.assertFalse(MarketRefund.objects.exists())

    def test_record_write_failure_rolls_back_invoice_and_refund(self):
        with patch('marketplace.payment_services.record', side_effect=RuntimeError('Injected failure')):
            with self.assertRaises(RuntimeError):
                self.post()
        self.assertFalse(MarketInvoice.objects.exists())
        self.issue(); refund = self.refund()
        for target in ['marketplace.payment_services.record', 'marketplace.payment_services.Refund.save']:
            with patch(target, side_effect=RuntimeError('Injected failure')):
                with self.assertRaises(RuntimeError):
                    self.decide(refund)
            invoice, refund_row = MarketInvoice.objects.get(), MarketRefund.objects.get()
            self.assertEqual((invoice.status, invoice.credited_amount, refund_row.status), ('ISSUED', 0, 'PENDING'))
            self.assertEqual(MarketTransaction.objects.count(), 1)

    def test_cancelled_booking_and_invalid_fee_policy_cannot_issue(self):
        with override_settings(MARKETPLACE_PLATFORM_FEE_BPS=10001):
            self.assertEqual(self.post().status_code, 409)
        Booking.objects.filter(pk=self.booking.pk).update(status='CANCELLED', cancelled_at=timezone.now())
        self.assertEqual(self.post().status_code, 409)
        self.assertFalse(MarketInvoice.objects.exists())

    def test_financial_records_remain_available_when_new_bookings_are_disabled(self):
        with override_settings(MARKETPLACE_BOOKINGS_ENABLED=False):
            self.issue()
            self.assertEqual(self.decide(self.refund()).status_code, 200)

    def test_session_financial_writes_require_csrf(self):
        client = APIClient(enforce_csrf_checks=True); client.force_login(self.talent)
        self.assertEqual(client.post(self.url, {}, format='json').status_code, 403)

    def test_database_constraints_reject_unbalanced_invoice(self):
        self.issue()
        with self.assertRaises(IntegrityError), transaction.atomic():
            MarketInvoice.objects.update(talent_amount=Decimal('1.00'))

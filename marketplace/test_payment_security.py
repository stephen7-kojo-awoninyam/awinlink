from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.db import IntegrityError, transaction
from django.test import override_settings
from rest_framework.test import APITestCase

from . import test_payments as foundation
from .models import MarketInvoice as Invoice, MarketRefund as Refund, MarketTransaction as Record


@override_settings(**foundation.PaymentTests._overridden_settings)
class PaymentSecurityTests(APITestCase):
    setUpTestData = classmethod(foundation.PaymentTests.setUpTestData.__func__)
    setUp = foundation.PaymentTests.setUp
    post = foundation.PaymentTests.post
    issue = foundation.PaymentTests.issue
    refund = foundation.PaymentTests.refund
    decide = foundation.PaymentTests.decide

    def test_fake_paid_fields_and_provider_claims_cannot_create_payment_evidence(self):
        for field, value in [('status', 'PAID'), ('paid', True), ('paid_at', '2026-10-21'),
            ('collection', 'CAPTURED'), ('mode', 'LIVE'), ('provider_reference', 'fake'),
            ('transaction_id', 'fake'), ('fee_bps', 0), ('snapshot', {'mode': 'PAID'})]:
            with self.subTest(field=field):
                self.assertEqual(self.post(**{field: value}).status_code, 400)
        self.assertFalse(Invoice.objects.exists())
        row = self.issue()
        self.assertEqual((row['mode'], row['collection'], row['status']), ('RECORD_ONLY', 'NONE', 'ISSUED'))
        refund = self.refund()
        self.assertEqual(self.post(f"refunds/{refund['id']}/", action='PAID', reason='Claim paid').status_code, 400)
        self.assertEqual(self.post(f"refunds/{refund['id']}/", action='APPROVE', reason='Claim paid', paid=True).status_code, 400)
        self.assertEqual(Record.objects.count(), 1)

    def test_transaction_history_is_read_only_for_every_participant(self):
        self.issue()
        for actor in [self.talent, self.scout, self.outsider]:
            self.client.force_authenticate(actor)
            for method in ['post', 'put', 'patch', 'delete']:
                result = getattr(self.client, method)(self.url+'transactions/', {'kind': 'PAYMENT_CAPTURED', 'amount': '120'}, format='json')
                self.assertEqual(result.status_code, 405)
        self.assertEqual(Record.objects.count(), 1)

    def test_resetting_invoice_balance_cannot_authorize_duplicate_credit(self):
        self.issue(); self.assertEqual(self.decide(self.refund('80.00')).status_code, 200)
        Invoice.objects.update(status='ISSUED', credited_amount=0, credited_fee=0)
        before = list(Record.objects.values())
        self.assertEqual(self.post('refunds/', self.scout, amount='120.00', reason='Duplicate', idempotency_key=str(uuid4())).status_code, 409)
        self.client.force_authenticate(self.talent)
        for suffix in ['', 'refunds/', 'transactions/']:
            self.assertEqual(self.client.get(self.url+suffix).status_code, 409)
        self.assertEqual(list(Record.objects.values()), before)
        self.assertEqual(Refund.objects.count(), 1)

    def test_changed_invoice_amount_or_mode_does_not_pass_as_agreed_financial_state(self):
        self.issue()
        original = Invoice.objects.get()
        for changes in [{'amount': Decimal('100'), 'fee_amount': Decimal('2.50'), 'talent_amount': Decimal('97.50')},
                        {'snapshot': {**original.snapshot, 'mode': 'PAID'}}]:
            with transaction.atomic():
                Invoice.objects.update(**changes)
                self.client.force_authenticate(self.talent)
                self.assertEqual(self.client.get(self.url).status_code, 409)
                transaction.set_rollback(True)

    def test_corrupt_approved_refund_or_missing_transaction_blocks_further_writes(self):
        self.issue(); refund = self.refund()
        self.assertEqual(self.decide(refund).status_code, 200)
        Record.objects.filter(kind='REFUND_APPROVED').delete()
        self.assertEqual(self.decide(refund).status_code, 409)
        self.assertEqual(self.post('refunds/', self.scout, amount='1', reason='More', idempotency_key=str(uuid4())).status_code, 409)
        self.assertEqual(Refund.objects.count(), 1)

    def test_refund_requested_by_a_nonbuyer_is_not_usable_financial_evidence(self):
        self.issue(); refund = self.refund()
        Refund.objects.update(requested_by=self.outsider)
        self.assertEqual(self.decide(refund).status_code, 409)
        self.assertEqual(Refund.objects.get().status, 'PENDING')
        self.assertEqual(Record.objects.count(), 1)

    def test_database_rejects_fake_paid_statuses_duplicate_issuance_and_duplicate_credits(self):
        self.issue(); refund = self.refund(); self.decide(refund)
        for model, values in [(Invoice, {'status': 'PAID'}), (Refund, {'status': 'PAID'}),
                              (Record, {'kind': 'PAYMENT_CAPTURED'})]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                model.objects.update(**values)
        for row in Record.objects.all():
            values = {f.attname: getattr(row, f.attname) for f in Record._meta.fields if f.name not in ['id', 'reference', 'created_at']}
            with self.assertRaises(IntegrityError), transaction.atomic():
                Record.objects.create(**values)

    def test_cross_party_forgery_and_replays_do_not_create_more_transactions(self):
        self.issue(); refund = self.refund()
        self.assertEqual(self.decide(refund, user=self.scout).status_code, 403)
        for _ in range(3):
            self.assertEqual(self.decide(refund).status_code, 200)
        self.assertEqual(Record.objects.count(), 2)
        self.assertEqual(self.decide(refund, 'REJECT').status_code, 409)

    def test_final_refund_write_failure_rolls_back_all_financial_evidence(self):
        self.issue(); refund = self.refund()
        with patch('marketplace.payment_services.Refund.save', side_effect=RuntimeError('Injected late failure')):
            with self.assertRaises(RuntimeError):
                self.decide(refund)
        self.assertEqual((Invoice.objects.get().credited_amount, Refund.objects.get().status, Record.objects.count()), (0, 'PENDING', 1))
        self.assertEqual(self.decide(refund).status_code, 200)

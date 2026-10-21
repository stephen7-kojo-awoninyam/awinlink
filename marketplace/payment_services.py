"""Record-only invoices and refund credits. No provider, collection, or payout."""
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import OperationalError, transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .booking_views import booking_for
from .models import Booking, MarketInvoice as Invoice, MarketRefund as Refund, MarketTransaction as Record
from .permissions import require_participant
from .services import Conflict


def require_talent(booking, actor):
    if booking.talent.user_id != actor.pk:
        raise PermissionDenied('Only the booked talent may issue invoices or decide refund requests.')


def money(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount <= 0 or amount > Decimal('9999999999.99') or amount != amount.quantize(Decimal('.01')):
            raise ValueError()
    except (ValueError, ArithmeticError):
        raise ValidationError({'amount': 'Use a positive amount with at most two decimal places.'})
    return amount.quantize(Decimal('.01'))


def reason_text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 3000:
        raise ValidationError({'reason': 'Provide a reason of at most 3000 characters.'})
    return value.strip()


def record(invoice, actor, kind, amount, fee, reason='', refund=None):
    return Record.objects.create(invoice=invoice, actor=actor, kind=kind, refund=refund,
        amount=amount, fee_amount=fee, talent_amount=amount-fee, currency=invoice.currency, reason=reason)


def locked_booking(booking_id, actor):
    from django.shortcuts import get_object_or_404
    from organizations.models import Organization
    org_id = get_object_or_404(Booking.objects.values('offer__organization_id'), pk=booking_id)['offer__organization_id']
    if org_id:
        Organization.objects.select_for_update().get(pk=org_id)
    booking = booking_for(actor, booking_id, lock=True)
    # Serialize suspension and block creation against the final ACL check.
    # NOWAIT avoids a lock cycle with foreign-key checks from a block insert.
    try:
        list(get_user_model().objects.select_for_update(nowait=True).filter(
            pk__in={actor.pk, booking.offer.sender_id, booking.talent.user_id}).order_by('pk'))
    except OperationalError as exc:
        cause = exc.__cause__
        if getattr(cause, 'pgcode', None) == '55P03' or getattr(cause, 'sqlstate', None) == '55P03':
            raise Conflict('A participant account is being updated. Refresh and retry.') from exc
        raise
    require_participant(actor, booking.offer)
    return booking


def check_integrity(invoice, booking):
    """Fail closed on inconsistent obligations/evidence, never infer cash payment."""
    def require(condition):
        if not condition:
            raise Conflict('Financial records are inconsistent. No financial changes were saved; review the records.')

    snap = invoice.snapshot
    require(isinstance(snap, dict))
    require(snap.get('mode') == 'RECORD_ONLY' and snap.get('fee_policy') == 'TALENT_DEDUCTION_V1')
    require((snap.get('booking'), snap.get('offer'), snap.get('buyer'), snap.get('organization'), snap.get('talent')) ==
        (booking.pk, booking.offer_id, booking.offer.sender_id, booking.offer.organization_id, booking.talent_id))
    require(invoice.issued_by_id == booking.talent.user_id)
    require(invoice.amount == booking.amount and invoice.currency == booking.currency and snap.get('terms') == booking.snapshot)
    expected_fee = (invoice.amount * Decimal(invoice.fee_bps) / Decimal(10000)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    require(invoice.fee_amount == expected_fee and invoice.talent_amount == invoice.amount-expected_fee)
    rows = list(invoice.transactions.order_by('pk'))
    require(bool(rows) and rows[0].kind == 'INVOICE_ISSUED')
    issued, credits, voided = 0, Decimal(0), False
    credited_fee = Decimal(0)
    refunds = {row.pk: row for row in invoice.refunds.all()}
    approved = set()
    for row in rows:
        require(row.currency == invoice.currency and row.amount > 0 and row.amount == row.fee_amount+row.talent_amount)
        require(row.actor_id == booking.talent.user_id)
        if row.kind == 'INVOICE_ISSUED':
            issued += 1
            require(issued == 1 and row.refund_id is None and row.amount == invoice.amount and row.fee_amount == expected_fee)
        elif row.kind == 'REFUND_APPROVED':
            require(not voided and row.refund_id in refunds and row.refund_id not in approved)
            refund = refunds[row.refund_id]
            require(refund.status == 'APPROVED' and refund.amount == row.amount and refund.decided_by_id == row.actor_id)
            require(refund.decision_reason == row.reason)
            credits += row.amount
            fee = (expected_fee * credits / invoice.amount).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
            require(credits <= invoice.amount and row.fee_amount == fee-credited_fee)
            credited_fee = fee
            approved.add(refund.pk)
        elif row.kind == 'INVOICE_VOIDED':
            require(not voided and credits == 0 and row.refund_id is None and row.amount == invoice.amount and row.fee_amount == expected_fee)
            voided = True
        else:
            require(False)
    pending = Decimal(0)
    for refund in refunds.values():
        require(refund.requested_by_id == booking.offer.sender_id and refund.amount > 0 and bool(refund.reason.strip()))
        if refund.status == 'APPROVED':
            require(refund.pk in approved and refund.decided_at is not None)
        elif refund.status == 'PENDING':
            require(refund.decided_at is None and refund.decided_by_id is None)
            pending += refund.amount
        else:
            require(refund.status == 'REJECTED' and refund.decided_by_id == booking.talent.user_id and refund.decided_at is not None)
    require(credits+pending <= invoice.amount and (not voided or pending == 0))
    status = 'VOID' if voided else 'CREDITED' if credits == invoice.amount else 'PARTIALLY_CREDITED' if credits else 'ISSUED'
    require((invoice.status, invoice.credited_amount, invoice.credited_fee) == (status, credits, credited_fee))


@transaction.atomic
def issue(booking_id, actor):
    booking = locked_booking(booking_id, actor)
    require_talent(booking, actor)
    existing = Invoice.objects.filter(booking=booking).first()
    if existing:
        check_integrity(existing, booking)
        return existing, False
    if booking.status == 'CANCELLED':
        raise Conflict('A cancelled booking cannot receive a new invoice.')
    bps = settings.MARKETPLACE_PLATFORM_FEE_BPS
    if type(bps) is not int or not 0 <= bps <= 10000:
        raise Conflict('The platform fee configuration is invalid.')
    amount = money(booking.amount)
    fee = (amount * Decimal(bps) / Decimal(10000)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    invoice = Invoice.objects.create(booking=booking, issued_by=actor, amount=amount, currency=booking.currency,
        fee_bps=bps, fee_amount=fee, talent_amount=amount-fee,
        snapshot={'booking': booking.pk, 'offer': booking.offer_id, 'buyer': booking.offer.sender_id,
            'organization': booking.offer.organization_id, 'talent': booking.talent_id,
            'terms': booking.snapshot, 'fee_policy': 'TALENT_DEDUCTION_V1', 'mode': 'RECORD_ONLY'})
    record(invoice, actor, 'INVOICE_ISSUED', amount, fee)
    return invoice, True


def locked_invoice(booking_id, actor):
    booking = locked_booking(booking_id, actor)
    from django.shortcuts import get_object_or_404
    invoice = get_object_or_404(Invoice.objects.select_for_update(), booking=booking)
    check_integrity(invoice, booking)
    return booking, invoice


@transaction.atomic
def request_refund(booking_id, actor, amount, reason, idempotency_key):
    booking, invoice = locked_invoice(booking_id, actor)
    if actor.pk != booking.offer.sender_id:
        raise PermissionDenied('Only the authorized booking buyer may request a refund credit.')
    amount, reason = money(amount), reason_text(reason)
    previous = invoice.refunds.filter(idempotency_key=idempotency_key).first()
    if previous:
        if (previous.amount, previous.reason, previous.requested_by_id) != (amount, reason, actor.pk):
            raise Conflict('This idempotency key was used for another request.')
        return previous, False
    if invoice.status not in ['ISSUED', 'PARTIALLY_CREDITED']:
        raise Conflict('This invoice no longer accepts refund requests.')
    pending = invoice.refunds.filter(status='PENDING').aggregate(amount=Sum('amount'))['amount'] or Decimal(0)
    if amount > invoice.amount - invoice.credited_amount - pending:
        raise Conflict('The requested amount exceeds the unreserved invoice balance.')
    return Refund.objects.create(invoice=invoice, amount=amount, reason=reason,
        idempotency_key=idempotency_key, requested_by=actor), True


@transaction.atomic
def decide_refund(booking_id, actor, refund_id, action, reason):
    booking, invoice = locked_invoice(booking_id, actor)
    require_talent(booking, actor)
    from django.shortcuts import get_object_or_404
    refund = get_object_or_404(Refund.objects.select_for_update(), pk=refund_id, invoice=invoice)
    reason = reason_text(reason)
    if action not in ['APPROVE', 'REJECT']:
        raise ValidationError({'action': 'Choose APPROVE or REJECT.'})
    status = 'APPROVED' if action == 'APPROVE' else 'REJECTED'
    if refund.status != 'PENDING':
        if (refund.status, refund.decision_reason, refund.decided_by_id) == (status, reason, actor.pk):
            return refund
        raise Conflict('This request already has a final decision.')
    if invoice.status not in ['ISSUED', 'PARTIALLY_CREDITED']:
        raise Conflict('This invoice no longer accepts refund decisions.')
    if action == 'APPROVE':
        credited = invoice.credited_amount + refund.amount
        if credited > invoice.amount:
            raise Conflict('The refund exceeds the remaining invoice amount.')
        # Cumulative allocation avoids penny drift across split refunds. A full
        # credit reverses exactly the original fee, never more than that fee.
        cumulative_fee = (invoice.fee_amount * credited / invoice.amount).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
        fee = cumulative_fee - invoice.credited_fee
        invoice.credited_amount, invoice.credited_fee = credited, cumulative_fee
        invoice.status = 'CREDITED' if credited == invoice.amount else 'PARTIALLY_CREDITED'
        invoice.save(update_fields=['credited_amount', 'credited_fee', 'status'])
        record(invoice, actor, 'REFUND_APPROVED', refund.amount, fee, reason, refund)
    refund.status, refund.decided_by, refund.decided_at, refund.decision_reason = status, actor, timezone.now(), reason
    refund.save(update_fields=['status', 'decided_by', 'decided_at', 'decision_reason'])
    return refund


@transaction.atomic
def void(booking_id, actor, reason):
    booking, invoice = locked_invoice(booking_id, actor)
    require_talent(booking, actor)
    reason = reason_text(reason)
    if invoice.status == 'VOID':
        previous = invoice.transactions.get(kind='INVOICE_VOIDED')
        if previous.reason != reason:
            raise Conflict('This invoice was already voided with a different reason.')
        return invoice
    if invoice.credited_amount or invoice.refunds.filter(status='PENDING').exists():
        raise Conflict('Resolve pending requests; credited invoices cannot be voided.')
    invoice.status = 'VOID'
    invoice.save(update_fields=['status'])
    record(invoice, actor, 'INVOICE_VOIDED', invoice.amount, invoice.fee_amount, reason)
    return invoice

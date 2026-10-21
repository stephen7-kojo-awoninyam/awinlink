"""Transactional marketplace operations. All callers retain the original deal ACL."""
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import IntegrityError, transaction
from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from talents.models import TalentProfile
from notifications.services import create_notification
from .models import AvailabilityWindow, Booking, BookingEvent
from .permissions import require_participant


class Conflict(APIException):
    status_code = 409
    default_detail = 'The requested time or record has changed. Refresh and try again.'


POLICY = 'CANCEL_BEFORE_START_V1'


def quote(listing, data):
    start = data.pop('starts_at', None)
    revision = data.pop('expected_revision', None)
    negotiated = data.pop('negotiated_amount', None)
    if not listing.booking_enabled:
        if start is not None or revision is not None or negotiated is not None:
            raise ValidationError('This listing has not enabled bookings.')
        return {}
    if not settings.MARKETPLACE_BOOKINGS_ENABLED:
        raise Conflict('New bookings are temporarily disabled.')
    if start is None or revision is None:
        raise ValidationError('Bookings require starts_at with a UTC offset and expected_revision. Update your client.')
    if revision != listing.revision:
        raise Conflict('The listing has changed. Review the latest price and terms.')
    if listing.talent.availability_status != 'AVAILABLE':
        raise ValidationError('This talent is not accepting new bookings.')
    if start <= timezone.now() or start > timezone.now() + timedelta(days=365):
        raise ValidationError('Choose an appointment within the next 365 days.')
    end = start + timedelta(minutes=listing.duration_minutes)
    buffer = timedelta(minutes=listing.buffer_minutes)
    ensure_open(listing.talent_id, start - buffer, end + buffer)
    if listing.pricing_mode == 'QUOTE_ONLY':
        if negotiated is None:
            raise ValidationError({'negotiated_amount': 'A proposed price is required.'})
        amount = negotiated
    else:
        if negotiated is not None:
            raise ValidationError('Fixed/hourly totals are calculated by the server.')
        amount = Decimal(listing.base_price)
        if listing.pricing_mode == 'HOURLY':
            amount = (amount * Decimal(listing.duration_minutes) / Decimal(60)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    if amount <= 0 or amount > Decimal('9999999999.99'):
        raise ValidationError('The calculated quote is outside the supported price range.')
    return dict(workflow_version=2, listing_revision=revision, quoted_amount=amount,
                quoted_currency=listing.currency, requested_start=start, requested_end=end,
                quote_snapshot={'title': listing.title, 'description': listing.description,
                                'pricing_mode': listing.pricing_mode, 'duration_minutes': listing.duration_minutes,
                                'buffer_minutes': listing.buffer_minutes, 'amount': str(amount),
                                'currency': listing.currency, 'cancellation_policy': POLICY,
                                'collection': 'NONE', 'version': 1})


def ensure_open(talent_id, start, end):
    if not AvailabilityWindow.objects.filter(talent_id=talent_id, starts_at__lte=start, ends_at__gte=end).exists():
        raise Conflict('The requested interval, including preparation buffers, is not available.')
    if Booking.objects.filter(talent_id=talent_id, busy_start__lt=end, busy_end__gt=start).exclude(status='CANCELLED').exists():
        raise Conflict('This time is already booked.')


def record(booking, actor, action, reason=''):
    event = BookingEvent.objects.create(booking=booking, actor=actor, action=action, reason=reason)
    other = booking.offer.sender if actor.pk == booking.talent.user_id else booking.talent.user
    try:
        require_participant(other, booking.offer)
    except PermissionDenied:
        return event
    create_notification(user=other, sender=actor, notification_type='SYSTEM',
                        message=f'Booking #{booking.pk}: {action.replace("_", " ").lower()}.',
                        metadata={'marketplace_booking_id': booking.pk},
                        deduplication_key=f'market-event:{event.pk}:{other.pk}')


def booking_notification_is_current(notification):
    if not isinstance(notification.metadata, dict):
        return True
    booking_id = notification.metadata.get('marketplace_booking_id')
    if not booking_id:
        return True
    try:
        booking_id = int(booking_id)
    except (TypeError, ValueError):
        return False
    booking = Booking.objects.filter(pk=booking_id).select_related('offer__listing__talent', 'offer__organization').first()
    if booking is None:
        return False
    try:
        require_participant(notification.user, booking.offer)
        return True
    except PermissionDenied:
        return False


def reserve(offer, actor):
    """Caller locks the offer; all provider operations next lock its talent row."""
    if not settings.MARKETPLACE_BOOKINGS_ENABLED:
        raise Conflict('New bookings are temporarily disabled.')
    talent = TalentProfile.objects.select_for_update().get(pk=offer.listing.talent_id)
    require_participant(actor, offer)
    if talent.availability_status != 'AVAILABLE' or not talent.user.is_active:
        raise Conflict('The talent is not accepting bookings.')
    if offer.requested_start <= timezone.now():
        raise Conflict('This proposal has expired. Request a future time.')
    buffer = timedelta(minutes=offer.quote_snapshot['buffer_minutes'])
    start, end = offer.requested_start - buffer, offer.requested_end + buffer
    ensure_open(talent.pk, start, end)
    try:
        with transaction.atomic():
            booking = Booking.objects.create(offer=offer, talent=talent,
                starts_at=offer.requested_start, ends_at=offer.requested_end, busy_start=start, busy_end=end,
                amount=offer.quoted_amount, currency=offer.quoted_currency,
                snapshot={**offer.quote_snapshot, 'terms': offer.terms})
    except IntegrityError as error:
        if getattr(error.__cause__, 'diag', None) and error.__cause__.diag.constraint_name == 'market_booking_no_overlap':
            raise Conflict('This time was just booked.') from None
        raise
    record(booking, actor, 'CONFIRMED')
    return booking


def capabilities(user, booking):
    talent = user.pk == booking.talent.user_id
    live = booking.status not in ['COMPLETED', 'CANCELLED']
    return {'message': live, 'start': talent and booking.status == 'CONFIRMED' and timezone.now() >= booking.starts_at,
            'submit': talent and booking.status == 'IN_PROGRESS',
            'complete': not talent and booking.status == 'SUBMITTED',
            'request_changes': not talent and booking.status == 'SUBMITTED',
            'cancel': booking.status == 'CONFIRMED' and timezone.now() < booking.starts_at,
            'review': not talent and booking.status == 'COMPLETED' and not hasattr(booking, 'review'),
            'manage_review': not talent and booking.status == 'COMPLETED' and hasattr(booking, 'review')}


def transition(booking, actor, action, reason):
    require_participant(actor, booking.offer)
    if not capabilities(actor, booking).get(action.lower(), False):
        raise PermissionDenied('This action is unavailable for your role or the current booking state.')
    if action in ['CANCEL', 'REQUEST_CHANGES'] and not reason:
        raise ValidationError({'reason': 'A reason is required.'})
    if action == 'START':
        booking.status, booking.started_at = 'IN_PROGRESS', timezone.now()
    elif action == 'COMPLETE':
        booking.status, booking.completed_at = 'COMPLETED', timezone.now()
    elif action == 'CANCEL':
        booking.status, booking.cancelled_at = 'CANCELLED', timezone.now()
    elif action == 'REQUEST_CHANGES':
        booking.status = 'IN_PROGRESS'
    booking.save(update_fields=['status', 'started_at', 'completed_at', 'cancelled_at'])
    record(booking, actor, action, reason)

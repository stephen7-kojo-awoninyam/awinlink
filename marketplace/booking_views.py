from datetime import timedelta
import base64
from django.conf import settings
from io import BytesIO
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Avg
from django.http import FileResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from talents.models import TalentProfile
from accounts.models import UserBlock
from .models import AvailabilityWindow, Booking, BookingReview, FulfillmentSubmission
from .permissions import require_participant
from .serializers import OffsetDateTimeField, MessageSerializer
from .services import Conflict, capabilities, record, transition
from .views import Authenticated, MarketPagination, visible, message_page


class WindowSerializer(serializers.ModelSerializer):
    starts_at = OffsetDateTimeField()
    ends_at = OffsetDateTimeField()

    class Meta:
        model = AvailabilityWindow
        fields = ['id', 'starts_at', 'ends_at', 'timezone']

    def validate(self, data):
        if data['starts_at'] <= timezone.now() or data['starts_at'] > timezone.now() + timedelta(days=365) or data['ends_at'] <= data['starts_at']:
            raise ValidationError('Choose an opening within the next 365 days, with end after start.')
        if data['ends_at'] - data['starts_at'] > timedelta(days=31):
            raise ValidationError('An opening may cover at most 31 days.')
        try:
            ZoneInfo(data.get('timezone', 'UTC'))
        except (ZoneInfoNotFoundError, ValueError):
            raise ValidationError({'timezone': 'Use an IANA timezone such as UTC or Africa/Accra.'})
        return data


class Availability(Authenticated, APIView):
    def get(self, request):
        if request.query_params.get('listing'):
            class Filter(serializers.Serializer):
                listing = serializers.IntegerField(min_value=1, max_value=9223372036854775807)
            f = Filter(data=request.query_params)
            f.is_valid(raise_exception=True)
            listing = get_object_or_404(visible(request.user), pk=f.validated_data['listing'])
            if not settings.MARKETPLACE_BOOKINGS_ENABLED or not listing.booking_enabled or listing.talent.availability_status != 'AVAILABLE':
                return Response({'results': [], 'next': None, 'count': 0})
            # Return only free openings, never another buyer's booking metadata.
            windows = AvailabilityWindow.objects.filter(talent=listing.talent, ends_at__gt=timezone.now())
            pager = MarketPagination()
            page = pager.paginate_queryset(windows, request)
            intervals = []
            for window in page:
                segments = [(max(window.starts_at, timezone.now() + timedelta(minutes=1)), window.ends_at)]
                busy = Booking.objects.filter(talent=listing.talent, busy_start__lt=window.ends_at,
                                              busy_end__gt=window.starts_at).exclude(status='CANCELLED').order_by('busy_start')
                for booking in busy:
                    segments = [(a, b) for start, end in segments for a, b in
                                [(start, min(end, booking.busy_start)), (max(start, booking.busy_end), end)] if a < b]
                for start, end in segments:
                    if end - start >= timedelta(minutes=listing.duration_minutes + 2 * listing.buffer_minutes):
                        intervals.append({'starts_at': start + timedelta(minutes=listing.buffer_minutes),
                                          'ends_at': end - timedelta(minutes=listing.buffer_minutes), 'timezone': window.timezone})
            return pager.get_paginated_response(intervals)
        talent = get_object_or_404(TalentProfile, user=request.user)
        qs = AvailabilityWindow.objects.filter(talent=talent, ends_at__gt=timezone.now())
        pager = MarketPagination()
        return pager.get_paginated_response(WindowSerializer(pager.paginate_queryset(qs, request), many=True).data)

    @transaction.atomic
    def post(self, request):
        talent = get_object_or_404(TalentProfile.objects.select_for_update(), user=request.user)
        serializer = WindowSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if AvailabilityWindow.objects.filter(talent=talent, starts_at__lt=data['ends_at'], ends_at__gt=data['starts_at']).exists():
            raise Conflict('Openings cannot overlap; delete or choose another interval.')
        serializer.save(talent=talent)
        return Response(serializer.data, status=201)


class AvailabilityDetail(Authenticated, APIView):
    @transaction.atomic
    def delete(self, request, pk):
        talent = get_object_or_404(TalentProfile.objects.select_for_update(), user=request.user)
        window = get_object_or_404(AvailabilityWindow, pk=pk, talent=talent)
        if Booking.objects.filter(talent=talent, busy_start__lt=window.ends_at, busy_end__gt=window.starts_at).exclude(status='CANCELLED').exists():
            raise Conflict('This opening contains a reservation and cannot be removed.')
        window.delete()
        return Response(status=204)


def booking_for(user, pk, lock=False):
    qs = Booking.objects.select_related('offer__listing__talent__user', 'offer__sender', 'offer__organization', 'talent__user')
    if lock:
        qs = qs.select_for_update(of=('self',))
    booking = get_object_or_404(qs, pk=pk)
    require_participant(user, booking.offer)
    return booking


def booking_data(booking, user):
    review = getattr(booking, 'review', None)
    return {'id': booking.pk, 'offer_id': booking.offer_id, 'listing_id': booking.offer.listing_id,
            'title': booking.snapshot.get('title'), 'status': booking.status,
            'starts_at': booking.starts_at, 'ends_at': booking.ends_at,
            'amount': str(booking.amount), 'currency': booking.currency, 'snapshot': booking.snapshot,
            'capabilities': capabilities(user, booking), 'collection': 'NONE',
            'review': {'rating': review.rating, 'text': review.text, 'published': review.publication_consented_at is not None} if review else None}


class Bookings(Authenticated, APIView):
    def get(self, request):
        qs = Booking.objects.select_related('offer__listing__talent', 'offer__organization', 'talent', 'review').filter(
            Q(offer__sender=request.user) | Q(talent__user=request.user))
        allowed = []
        for booking in qs:
            try:
                require_participant(request.user, booking.offer)
                allowed.append(booking.pk)
            except PermissionDenied:
                pass
        pager = MarketPagination()
        page = pager.paginate_queryset(qs.filter(pk__in=allowed), request)
        return pager.get_paginated_response([booking_data(b, request.user) for b in page])


class BookingDetail(Authenticated, APIView):
    def get(self, request, pk):
        return Response(booking_data(booking_for(request.user, pk), request.user))

    @transaction.atomic
    def post(self, request, pk):
        class Action(serializers.Serializer):
            action = serializers.ChoiceField(choices=['START', 'COMPLETE', 'REQUEST_CHANGES', 'CANCEL'])
            reason = serializers.CharField(max_length=3000, required=False, allow_blank=True, default='')
        data = Action(data=request.data)
        data.is_valid(raise_exception=True)
        booking = booking_for(request.user, pk, lock=True)
        transition(booking, request.user, data.validated_data['action'], data.validated_data['reason'])
        return Response(booking_data(booking, request.user))


class BookingMessages(Authenticated, APIView):
    def get(self, request, pk):
        booking = booking_for(request.user, pk)
        return Response(message_page(booking.offer, request.query_params, 'FULFILLMENT'))

    @transaction.atomic
    def post(self, request, pk):
        booking = booking_for(request.user, pk, lock=True)
        if not capabilities(request.user, booking)['message']:
            raise ValidationError('This booking is read-only.')
        serializer = MessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(offer=booking.offer, author=request.user, scope='FULFILLMENT')
        return Response(serializer.data, status=201)


class BookingEvents(Authenticated, APIView):
    def get(self, request, pk):
        booking = booking_for(request.user, pk)
        pager = MarketPagination()
        rows = pager.paginate_queryset(booking.events.order_by('-pk'), request)
        return pager.get_paginated_response([{'id': row.pk, 'actor': row.actor_id, 'action': row.action,
                                             'reason': row.reason, 'created_at': row.created_at} for row in rows])


class SubmissionInput(serializers.Serializer):
    summary = serializers.CharField(max_length=10000)
    artifact = serializers.FileField(required=False, write_only=True)

    def validate_artifact(self, value):
        if value.size > 2 * 1024 * 1024:
            raise ValidationError('Attachments may be at most 2 MiB.')
        return value


class Submissions(Authenticated, APIView):
    def get(self, request, pk):
        booking = booking_for(request.user, pk)
        pager = MarketPagination()
        rows = pager.paginate_queryset(booking.submissions.defer('artifact').order_by('-sequence'), request)
        return pager.get_paginated_response([{'id': row.pk, 'sequence': row.sequence, 'summary': row.summary,
                                              'artifact_name': row.artifact_name, 'created_at': row.created_at} for row in rows])

    @transaction.atomic
    def post(self, request, pk):
        booking = booking_for(request.user, pk, lock=True)
        if not capabilities(request.user, booking)['submit']:
            raise PermissionDenied('Only the talent may deliver an in-progress booking.')
        serializer = SubmissionInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        file = data.get('artifact')
        submission = FulfillmentSubmission.objects.create(booking=booking, author=request.user,
            sequence=booking.submissions.count() + 1, summary=data['summary'],
            artifact=file.read() if file else None,
            artifact_name=''.join(c if ord(c) >= 32 and ord(c) != 127 else '_' for c in file.name.replace('\\', '/').split('/')[-1])[:200] if file else '')
        booking.status = 'SUBMITTED'
        booking.save(update_fields=['status'])
        record(booking, request.user, 'SUBMITTED')
        return Response({'id': submission.pk, 'sequence': submission.sequence}, status=201)


class Artifact(Authenticated, APIView):
    def get(self, request, pk, submission_id):
        booking = booking_for(request.user, pk)
        submission = get_object_or_404(FulfillmentSubmission, pk=submission_id, booking=booking, artifact__isnull=False)
        if request.query_params.get('encoding') == 'base64':
            response = Response({'filename': submission.artifact_name,
                                 'content': base64.b64encode(bytes(submission.artifact)).decode('ascii')})
            response['Cache-Control'] = 'private, no-store'
            return response
        response = FileResponse(BytesIO(bytes(submission.artifact)), as_attachment=True,
                                filename=submission.artifact_name, content_type='application/octet-stream')
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        return response


class Reviews(Authenticated, APIView):
    @transaction.atomic
    def patch(self, request, pk):
        class Visibility(serializers.Serializer):
            publish = serializers.BooleanField()
        booking = booking_for(request.user, pk, lock=True)
        if not capabilities(request.user, booking)['manage_review']:
            raise PermissionDenied('Only the authorized reviewer may change review publication.')
        data = Visibility(data=request.data)
        data.is_valid(raise_exception=True)
        review = get_object_or_404(BookingReview, booking=booking, reviewer=request.user)
        review.publication_consented_at = timezone.now() if data.validated_data['publish'] else None
        review.save(update_fields=['publication_consented_at'])
        record(booking, request.user, 'REVIEW_VISIBILITY')
        return Response({'published': review.publication_consented_at is not None})

    @transaction.atomic
    def post(self, request, pk):
        class ReviewInput(serializers.Serializer):
            rating = serializers.IntegerField(min_value=1, max_value=5)
            text = serializers.CharField(max_length=3000)
            publish = serializers.BooleanField(default=False)
        booking = booking_for(request.user, pk, lock=True)
        if not capabilities(request.user, booking)['review']:
            raise PermissionDenied('Only the original authorized buyer may review a completed, unreviewed booking.')
        data = ReviewInput(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        review = BookingReview.objects.create(booking=booking, reviewer=request.user, rating=values['rating'],
            text=values['text'], publication_consented_at=timezone.now() if values['publish'] else None)
        record(booking, request.user, 'REVIEWED')
        return Response({'id': review.pk}, status=201)


class PublicReviews(Authenticated, APIView):
    def get(self, request, pk):
        listing = get_object_or_404(visible(request.user).filter(status='PUBLISHED', talent__profile_visibility='PUBLIC', talent__user__is_active=True), pk=pk)
        qs = BookingReview.objects.filter(booking__offer__listing=listing, booking__status='COMPLETED',
            publication_consented_at__isnull=False, moderation_state='VISIBLE')
        blocked_ids = list(UserBlock.objects.filter(user=request.user).values_list('blocked_user_id', flat=True))
        blocked_ids += list(UserBlock.objects.filter(blocked_user=request.user).values_list('user_id', flat=True))
        rows = qs.exclude(reviewer_id__in=blocked_ids)
        pager = MarketPagination()
        page = pager.paginate_queryset(rows, request)
        response = pager.get_paginated_response([{'rating': r.rating, 'text': r.text, 'reviewer': 'Verified buyer'} for r in page])
        response.data['average'] = rows.aggregate(value=Avg('rating'))['value']
        return response


@login_required
def booking_page(request):
    return render(request, 'marketplace/bookings.html')

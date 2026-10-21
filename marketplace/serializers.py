from rest_framework import serializers
from datetime import datetime
from decimal import Decimal
from django.conf import settings
from .models import Listing, Offer, DealMessage


class ListingSerializer(serializers.ModelSerializer):
    talent_area = serializers.CharField(source="talent.talent_area", read_only=True)
    talent_user = serializers.IntegerField(source="talent.user_id", read_only=True)
    talent_name = serializers.CharField(source="talent.user.username", read_only=True)
    country = serializers.CharField(source="talent.country", read_only=True)
    work_type = serializers.CharField(source="talent.preferred_work_type", read_only=True)
    experience = serializers.CharField(source="talent.experience_level", read_only=True)
    consent = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = Listing
        fields = ["id", "talent", "talent_user", "talent_name", "talent_area", "ecosystem", "subecosystem", "title", "description", "status", "country", "work_type", "experience", "publication_consented_at", "consent", 'pricing_mode', 'base_price', 'currency', 'duration_minutes', 'buffer_minutes', 'booking_enabled', 'revision']
        read_only_fields = ["talent", "publication_consented_at", 'revision']
        extra_kwargs = {'duration_minutes': {'min_value': 1, 'max_value': 1440}, 'buffer_minutes': {'min_value': 0, 'max_value': 240}}

    def validate(self, data):
        if self.instance is None and 'currency' not in data:
            data['currency'] = settings.MARKETPLACE_CURRENCY
        status = data.get("status", self.instance.status if self.instance else "DRAFT")
        if status == "PUBLISHED" and not data.get("consent"):
            raise serializers.ValidationError("Publishing or changing a published listing requires explicit consent.")
        def value(key, default):
            return data.get(key, getattr(self.instance, key, default))
        mode, price = value('pricing_mode', 'QUOTE_ONLY'), value('base_price', None)
        if (mode == 'QUOTE_ONLY' and price is not None) or (mode != 'QUOTE_ONLY' and (price is None or price <= 0)):
            raise serializers.ValidationError({'base_price': 'Quote-only requires no base price; fixed/hourly requires a positive price.'})
        if value('currency', 'GHS') != getattr(settings, 'MARKETPLACE_CURRENCY', 'GHS'):
            raise serializers.ValidationError({'currency': 'Unsupported marketplace currency.'})
        return data


class OffsetDateTimeField(serializers.DateTimeField):
    def to_internal_value(self, value):
        try:
            original = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace('Z', '+00:00'))
            if original.utcoffset() is None:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise serializers.ValidationError('Use an ISO date/time with an explicit UTC offset (or Z).')
        return super().to_internal_value(value)


class OfferSerializer(serializers.ModelSerializer):
    starts_at = OffsetDateTimeField(write_only=True, required=False)
    expected_revision = serializers.IntegerField(write_only=True, min_value=1, required=False)
    negotiated_amount = serializers.DecimalField(write_only=True, max_digits=12, decimal_places=2, min_value=Decimal('0.01'), required=False)
    booking_id = serializers.IntegerField(source='booking.pk', read_only=True, default=None)

    class Meta:
        model = Offer
        fields = ["id", "listing", "sender", "organization", "terms", "status", "talent_consented_at", "decided_at", "created_at", 'workflow_version', 'listing_revision', 'quoted_amount', 'quoted_currency', 'requested_start', 'requested_end', 'quote_snapshot', 'starts_at', 'expected_revision', 'negotiated_amount', 'booking_id']
        read_only_fields = ["sender", "status", "talent_consented_at", "decided_at", "created_at", 'workflow_version', 'listing_revision', 'quoted_amount', 'quoted_currency', 'requested_start', 'requested_end', 'quote_snapshot']


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = DealMessage
        fields = ["id", "author", "body", "created_at"]
        read_only_fields = ["author", "created_at"]

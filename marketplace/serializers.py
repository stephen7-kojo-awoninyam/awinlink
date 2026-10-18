from rest_framework import serializers
from .models import Listing, Offer, DealMessage


class ListingSerializer(serializers.ModelSerializer):
    talent_user = serializers.IntegerField(source="talent.user_id", read_only=True)
    talent_name = serializers.CharField(source="talent.user.username", read_only=True)
    country = serializers.CharField(source="talent.country", read_only=True)
    work_type = serializers.CharField(source="talent.preferred_work_type", read_only=True)
    experience = serializers.CharField(source="talent.experience_level", read_only=True)
    consent = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = Listing
        fields = ["id", "talent", "talent_user", "talent_name", "ecosystem", "subecosystem", "title", "description", "status", "country", "work_type", "experience", "publication_consented_at", "consent"]
        read_only_fields = ["talent", "publication_consented_at"]

    def validate(self, data):
        status = data.get("status", self.instance.status if self.instance else "DRAFT")
        if status == "PUBLISHED" and not data.get("consent"):
            raise serializers.ValidationError("Publishing or changing a published listing requires explicit consent.")
        return data


class OfferSerializer(serializers.ModelSerializer):
    class Meta:
        model = Offer
        fields = ["id", "listing", "sender", "organization", "terms", "status", "talent_consented_at", "decided_at", "created_at"]
        read_only_fields = ["sender", "status", "talent_consented_at", "decided_at", "created_at"]


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = DealMessage
        fields = ["id", "author", "body", "created_at"]
        read_only_fields = ["author", "created_at"]

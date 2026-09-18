from rest_framework import serializers

from .models import (
    EventCategory,
    Event,
    EventRegistration,
    EventFeedback,
    EventCertificate,
    EventMedia,
)


# =====================================================
# EVENT CATEGORY SERIALIZER
# =====================================================

class EventCategorySerializer(serializers.ModelSerializer):

    class Meta:

        model = EventCategory

        fields = [
            "id",
            "name",
            "domain",
            "description",
        ]


# =====================================================
# EVENT SERIALIZER
# =====================================================

class EventSerializer(serializers.ModelSerializer):

    organizer_name = serializers.CharField(
        source="organizer.name",
        read_only=True
    )

    category_name = serializers.CharField(
        source="category.name",
        read_only=True
    )

    registrations_count = serializers.IntegerField(
        source="registrations.count",
        read_only=True
    )

    class Meta:

        model = Event

        fields = [
            "id",
            "organizer",
            "organizer_name",
            "category",
            "category_name",
            "title",
            "slug",
            "description",
            "image",
            "event_type",
            "location",
            "online",
            "meeting_link",
            "start_date",
            "end_date",
            "registration_deadline",
            "capacity",
            "status",
            "registrations_count",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "organizer",
            "created_at",
            "updated_at",
        ]


# =====================================================
# EVENT REGISTRATION SERIALIZER
# =====================================================

class EventRegistrationSerializer(
    serializers.ModelSerializer
):

    event_title = serializers.CharField(
        source="event.title",
        read_only=True
    )

    talent_name = serializers.SerializerMethodField()

    class Meta:

        model = EventRegistration

        fields = [
            "id",
            "event",
            "event_title",
            "talent",
            "talent_name",
            "status",
            "registered_at",
            "attendance_marked",
            "attendance_time",
        ]

        read_only_fields = [
            "talent",
            "status",
            "registered_at",
            "attendance_marked",
            "attendance_time",
        ]

    def get_talent_name(self, obj):

        return (
            obj.talent.user.get_full_name()
            or obj.talent.user.username
        )


# =====================================================
# EVENT FEEDBACK SERIALIZER
# =====================================================

class EventFeedbackSerializer(
    serializers.ModelSerializer
):
    
    

    reviewer_name = serializers.SerializerMethodField()
    
    rating = serializers.IntegerField(
    min_value=1,
    max_value=5
     )

    class Meta:

        model = EventFeedback

        fields = [
            "id",
            "event",
            "reviewer",
            "reviewer_name",
            "rating",
            "comment",
            "created_at",
        ]

        read_only_fields = [
            "reviewer",
            "created_at",
        ]

    def get_reviewer_name(self, obj):

        return (
            obj.reviewer.get_full_name()
            or obj.reviewer.username
        )


# =====================================================
# EVENT CERTIFICATE SERIALIZER
# =====================================================

class EventCertificateSerializer(
    serializers.ModelSerializer
):

    event_title = serializers.CharField(
        source="event.title",
        read_only=True
    )

    talent_name = serializers.SerializerMethodField()

    issued_by_name = serializers.CharField(
        source="issued_by.name",
        read_only=True
    )

    class Meta:

        model = EventCertificate

        fields = [
            "id",
            "event",
            "event_title",
            "talent",
            "talent_name",
            "certificate_title",
            "issued_by",
            "issued_by_name",
            "certificate_code",
            "description",
            "issued_at",
            "verified",
        ]

        read_only_fields = [
            "certificate_code",
            "issued_at",
            "verified",
        ]

    def get_talent_name(self, obj):

        return (
            obj.talent.user.get_full_name()
            or obj.talent.user.username
        )


# =====================================================
# EVENT MEDIA SERIALIZER
# =====================================================

class EventMediaSerializer(
    serializers.ModelSerializer
):

    uploaded_by_name = serializers.CharField(
        source="uploaded_by.name",
        read_only=True
    )

    event_title = serializers.CharField(
        source="event.title",
        read_only=True
    )

    class Meta:

        model = EventMedia

        fields = [
            "id",
            "event",
            "event_title",
            "uploaded_by",
            "uploaded_by_name",
            "media_type",
            "file",
            "caption",
            "uploaded_at",
        ]

        read_only_fields = [
            "uploaded_by",
            "uploaded_at",
        ]
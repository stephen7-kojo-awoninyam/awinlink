"""Explicit REST inputs and read-only classroom representations."""

from collections.abc import Mapping
from datetime import datetime

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import serializers

from .models import AttendanceInterval, Classroom, ClassroomInvitation, LiveSession, SessionParticipant


class StrictInputSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({key: ["This field is not accepted."] for key in sorted(unknown)})
        return super().to_internal_value(data)


class EmptyActionSerializer(StrictInputSerializer):
    pass


class ClassroomCreateSerializer(StrictInputSerializer):
    course = serializers.IntegerField(min_value=1)
    title = serializers.CharField(max_length=250, allow_blank=False)
    capacity = serializers.IntegerField(min_value=1, max_value=2147483647, default=50)
    host = serializers.IntegerField(min_value=1, required=False)


class AwareDateTimeField(serializers.DateTimeField):
    def to_internal_value(self, value):
        candidate = value if isinstance(value, datetime) else None
        if isinstance(value, str):
            try:
                candidate = parse_datetime(value)
            except ValueError:
                pass
        if candidate is not None and timezone.is_naive(candidate):
            self.fail("invalid", format="ISO-8601 with an explicit timezone offset")
        return super().to_internal_value(value)


class SessionScheduleSerializer(StrictInputSerializer):
    lesson = serializers.IntegerField(min_value=1)
    title = serializers.CharField(max_length=250, allow_blank=False)
    scheduled_start = AwareDateTimeField()
    scheduled_end = AwareDateTimeField()


class ConnectionActionSerializer(StrictInputSerializer):
    connection_id = serializers.UUIDField()


class ClassroomInvitationCreateSerializer(StrictInputSerializer):
    recipient = serializers.IntegerField(min_value=1)
    message = serializers.CharField(max_length=1000, allow_blank=True, default="")
    expires_at = AwareDateTimeField(required=False)


class ClassroomInvitationSerializer(serializers.ModelSerializer):
    recipient_username = serializers.CharField(source="recipient.username", read_only=True)
    classroom_title = serializers.CharField(source="classroom.title", read_only=True)
    course = serializers.IntegerField(source="classroom.course_id", read_only=True)
    is_expired = serializers.SerializerMethodField()

    class Meta:
        model = ClassroomInvitation
        fields = ["id", "classroom", "classroom_title", "course", "recipient", "invited_by", "message",
                  "status", "created_at", "expires_at", "responded_at", "is_expired", "recipient_username"]
        read_only_fields = fields

    def get_is_expired(self, invitation):
        return invitation.status == ClassroomInvitation.Status.EXPIRED or (
            invitation.status == ClassroomInvitation.Status.PENDING and invitation.expires_at <= timezone.now())


class ClassroomSerializer(serializers.ModelSerializer):
    capabilities = serializers.SerializerMethodField()

    def get_capabilities(self, classroom):
        from django.core.exceptions import PermissionDenied
        from .classroom_permissions import require_classroom_management, require_course_creator
        request = self.context.get("request")
        def allowed(check):
            if request is None:
                return False
            try:
                check(request.user, classroom.course if check == require_course_creator else classroom)
                return True
            except PermissionDenied:
                return False
        return {"manage": allowed(require_classroom_management), "staff": allowed(require_course_creator)}

    class Meta:
        model = Classroom
        fields = ["id", "course", "title", "created_by", "capacity", "is_active", "created_at", "updated_at", "capabilities"]
        read_only_fields = fields


class SessionParticipantSerializer(serializers.ModelSerializer):
    user = serializers.IntegerField(source="membership.user_id", read_only=True)
    display_name = serializers.SerializerMethodField()

    def get_display_name(self, participant):
        return participant.membership.user.get_full_name() or participant.membership.user.username

    class Meta:
        model = SessionParticipant
        fields = ["id", "session", "user", "display_name", "role", "admission_state", "admitted_at", "created_at"]
        read_only_fields = fields


class LiveSessionSerializer(serializers.ModelSerializer):
    my_participant = serializers.SerializerMethodField()
    capabilities = serializers.SerializerMethodField()

    def get_capabilities(self, session):
        from django.core.exceptions import PermissionDenied
        from .classroom_permissions import require_session_staff
        user = self.context["request"].user
        def staff(cohost=False):
            try:
                require_session_staff(user, session, allow_cohost=cohost)
                return True
            except PermissionDenied:
                return False
        manager, moderator = staff(), staff(True)
        return {"start": manager and session.status == "SCHEDULED", "cancel": manager and session.status == "SCHEDULED",
                "end": manager and session.status == "LIVE", "participants": moderator,
                "admit": moderator and session.status in {"LIVE", "SCHEDULED"},
                "remove": moderator and session.status in {"LIVE", "SCHEDULED"}}

    class Meta:
        model = LiveSession
        fields = ["id", "classroom", "lesson", "title", "status", "scheduled_start", "scheduled_end",
                  "started_at", "ended_at", "created_at", "my_participant", "capabilities"]
        read_only_fields = fields

    def get_my_participant(self, session):
        request = self.context["request"]
        # List views prefetch only this actor's record, never the whole roster.
        participants = getattr(session, "requester_participants", None)
        participant = participants[0] if participants else None
        if participants is None:
            participant = session.participants.filter(membership__user=request.user).select_related("membership").first()
        return SessionParticipantSerializer(participant).data if participant else None


class AttendanceSerializer(serializers.ModelSerializer):
    user = serializers.IntegerField(source="participant.membership.user_id", read_only=True)

    class Meta:
        model = AttendanceInterval
        fields = ["id", "participant", "user", "joined_at", "left_at"]
        read_only_fields = fields


class AttendanceConnectionSerializer(serializers.ModelSerializer):
    """A connection UUID is returned only to the owner of the join/leave call."""

    class Meta:
        model = AttendanceInterval
        fields = ["id", "participant", "connection_id", "joined_at", "left_at"]
        read_only_fields = fields


class ClassroomStaffInputSerializer(StrictInputSerializer):
    user = serializers.IntegerField(min_value=1)
    role = serializers.ChoiceField(choices=["COHOST", "HOST", "REMOVE"])


class ClassroomStaffSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    display_name = serializers.SerializerMethodField()

    def get_display_name(self, member):
        return member.user.get_full_name() or member.user.username

    class Meta:
        from .models import ClassroomMembership
        model = ClassroomMembership
        fields = ["id", "user", "username", "display_name", "role"]
        read_only_fields = fields


class ClassroomUserSearchInputSerializer(StrictInputSerializer):
    q = serializers.CharField(min_length=2, max_length=150)
    purpose = serializers.ChoiceField(choices=["invite", "cohost"])


class ClassroomUserSearchSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    display_name = serializers.SerializerMethodField()

    def get_display_name(self, user):
        return user.get_full_name() or user.username

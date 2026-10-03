from rest_framework import serializers

from accounts.models import User

from .models import (
    Conversation,
    ConversationParticipant,
    Message,
    Call,
    CallParticipant,
)


# ============================================================
# USER SUMMARY SERIALIZER
# ============================================================

class MessagingUserSerializer(serializers.ModelSerializer):

    class Meta:
        model = User

        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "profile_picture",
        ]


# ============================================================
# CONVERSATION PARTICIPANT SERIALIZER
# ============================================================

class ConversationParticipantSerializer(
    serializers.ModelSerializer
):

    user = MessagingUserSerializer(
        read_only=True
    )

    class Meta:
        model = ConversationParticipant

        fields = [
            "id",
            "user",
            "joined_at",
        ]


# ============================================================
# MESSAGE SERIALIZER
# ============================================================

class MessageSerializer(serializers.ModelSerializer):

    sender = MessagingUserSerializer(
        read_only=True
    )

    reply_to_id = serializers.PrimaryKeyRelatedField(
        source="reply_to",
        queryset=Message.objects.all(),
        required=False,
        allow_null=True,
        write_only=True,
    )

    reply_to = serializers.SerializerMethodField()

    class Meta:
        model = Message

        fields = [
            "id",
            "conversation",
            "sender",
            "message_type",
            "content",
            "reply_to_id",
            "reply_to",
            "image",
            "video",
            "file",
            "audio",
            "created_at",
            "is_read",
        ]

        read_only_fields = [
            "id",
            "conversation",
            "sender",
            "created_at",
            "is_read",
        ]

    def get_reply_to(self, obj):
        if not obj.reply_to_id:
            return None

        replied_message = obj.reply_to
        content = replied_message.content.strip()
        if not content:
            content = {
                "IMAGE": "Photo",
                "VIDEO": "Video",
                "FILE": "File",
                "AUDIO": "Voice message",
            }.get(replied_message.message_type, "Message")

        return {
            "id": replied_message.pk,
            "sender_name": (
                replied_message.sender.get_full_name()
                or replied_message.sender.username
            ),
            "content": content[:200],
        }


# ============================================================
# CONVERSATION SERIALIZER
# ============================================================

class ConversationSerializer(serializers.ModelSerializer):

    participants = ConversationParticipantSerializer(
        many=True,
        read_only=True
    )

    last_message = serializers.SerializerMethodField()

    class Meta:
        model = Conversation

        fields = [
            "id",
            "opportunity",
            "is_group",
            "name",
            "image",
            "created_by",
            "participants",
            "last_message",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "created_by",
            "participants",
            "last_message",
            "created_at",
            "updated_at",
        ]

    def get_last_message(self, obj):

        message = obj.last_message

        if not message:
            return None

        return MessageSerializer(
            message
        ).data


# ============================================================
# CREATE CONVERSATION SERIALIZER
# ============================================================

class ConversationCreateSerializer(
    serializers.Serializer
):

    user_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True
    )

    opportunity_id = serializers.IntegerField(
        required=False,
        allow_null=True
    )

    is_group = serializers.BooleanField(
        default=False
    )

    name = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True
    )

    def validate(self, attrs):

        is_group = attrs.get(
            "is_group",
            False
        )

        user_ids = attrs.get(
            "user_ids",
            []
        )

        name = attrs.get(
            "name",
            ""
        ).strip()

        # ----------------------------------------------------
        # GROUP VALIDATION
        # ----------------------------------------------------

        if is_group:

            if len(user_ids) < 1:
                raise serializers.ValidationError(
                    {
                        "user_ids":
                        "A group must have at least one other participant."
                    }
                )

            if not name:
                raise serializers.ValidationError(
                    {
                        "name":
                        "A group name is required."
                    }
                )

        # ----------------------------------------------------
        # ONE-TO-ONE VALIDATION
        # ----------------------------------------------------

        else:

            if len(user_ids) != 1:
                raise serializers.ValidationError(
                    {
                        "user_ids":
                        "A one-to-one conversation must have exactly one other participant."
                    }
                )

        attrs["name"] = name

        return attrs


# ============================================================
# CALL SERIALIZER
# ============================================================

class CallParticipantSerializer(serializers.ModelSerializer):

    user = MessagingUserSerializer(read_only=True)

    class Meta:
        model = CallParticipant

        fields = [
            "id",
            "user",
            "status",
            "joined_at",
            "left_at",
        ]

        read_only_fields = [
            "id",
            "user",
            "status",
            "joined_at",
            "left_at",
        ]


class CallSerializer(serializers.ModelSerializer):

    initiated_by = MessagingUserSerializer(read_only=True)

    participants = CallParticipantSerializer(
        many=True,
        read_only=True
    )

    class Meta:
        model = Call

        fields = [
            "id",
            "conversation",
            "initiated_by",
            "call_type",
            "status",
            "started_at",
            "answered_at",
            "ended_at",
            "duration",
            "participants",
        ]

        read_only_fields = [
            "id",
            "initiated_by",
            "status",
            "started_at",
            "answered_at",
            "ended_at",
            "duration",
            "participants",
        ]
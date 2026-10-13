from rest_framework import serializers
from django.contrib.auth import get_user_model

from .models import OrganizationMembership, OrganizationTeamInvitation


class TeamMemberSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = OrganizationMembership
        fields = ("id", "organization", "user", "username", "role", "status", "created_at", "updated_at")
        read_only_fields = fields


class TeamInvitationSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationTeamInvitation
        fields = ("id", "organization", "recipient", "inviter", "role", "status", "expires_at", "created_at", "updated_at")
        read_only_fields = fields


class TeamInvitationResponseSerializer(serializers.Serializer):
    token = serializers.CharField(write_only=True, max_length=128, trim_whitespace=False)


class TeamMemberRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=("MANAGER", "RECRUITER", "VIEWER"))


class OwnershipTransferSerializer(serializers.Serializer):
    membership_id = serializers.IntegerField(min_value=1)


class TeamInvitationCreateSerializer(serializers.Serializer):
    recipient_username = serializers.CharField(max_length=150)
    role = serializers.ChoiceField(choices=("MANAGER", "RECRUITER", "VIEWER"), default="VIEWER")
    expires_at = serializers.DateTimeField(required=False)

    def validate_recipient_username(self, value):
        username = value.strip().removeprefix("@").strip()
        try:
            return get_user_model().objects.get(username__iexact=username, is_active=True)
        except get_user_model().DoesNotExist:
            raise serializers.ValidationError("Enter an existing active account's username.") from None

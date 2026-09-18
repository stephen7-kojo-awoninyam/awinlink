from rest_framework import serializers

from .models import (
    ScoutProfile,
    ScoutTalentView,
    ScoutTalentFollow,
    ScoutTalentBookmark,
)


# ============================================================
# SCOUT PROFILE
# ============================================================

class ScoutProfileSerializer(serializers.ModelSerializer):

    username = serializers.CharField(
        source="user.username",
        read_only=True
    )

    full_name = serializers.SerializerMethodField()

    class Meta:

        model = ScoutProfile

        fields = [
            "id",
            "user",
            "username",
            "full_name",
            "headline",
            "biography",
            "specialization",
            "country",
            "city",
            "organization",
            "verified",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "user",
            "username",
            "full_name",
            "verified",
            "created_at",
            "updated_at",
        ]

    def get_full_name(self, obj):

        return (
            obj.user.get_full_name()
            or obj.user.username
        )


# ============================================================
# SCOUT TALENT VIEW
# ============================================================

class ScoutTalentViewSerializer(serializers.ModelSerializer):

    talent_name = serializers.SerializerMethodField()

    class Meta:

        model = ScoutTalentView

        fields = [
            "id",
            "scout",
            "talent",
            "talent_name",
            "viewed_at",
        ]

        read_only_fields = [
            "id",
            "scout",
            "viewed_at",
        ]

    def get_talent_name(self, obj):

        return (
            obj.talent.user.get_full_name()
            or obj.talent.user.username
        )


# ============================================================
# SCOUT TALENT FOLLOW
# ============================================================

class ScoutTalentFollowSerializer(serializers.ModelSerializer):

    talent_name = serializers.SerializerMethodField()

    class Meta:

        model = ScoutTalentFollow

        fields = [
            "id",
            "scout",
            "talent",
            "talent_name",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "scout",
            "created_at",
        ]

    def get_talent_name(self, obj):

        return (
            obj.talent.user.get_full_name()
            or obj.talent.user.username
        )


# ============================================================
# SCOUT TALENT BOOKMARK
# ============================================================

class ScoutTalentBookmarkSerializer(serializers.ModelSerializer):

    talent_name = serializers.SerializerMethodField()

    class Meta:

        model = ScoutTalentBookmark

        fields = [
            "id",
            "scout",
            "talent",
            "talent_name",
            "notes",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "scout",
            "created_at",
            "updated_at",
        ]

    def get_talent_name(self, obj):

        return (
            obj.talent.user.get_full_name()
            or obj.talent.user.username
        )
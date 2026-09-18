from rest_framework import serializers

from .models import (
    CoachProfile,
    CoachTalentView,
    CoachTalentFollow,
    CoachTalentBookmark,
)


# ============================================================
# COACH PROFILE
# ============================================================

class CoachProfileSerializer(serializers.ModelSerializer):

    username = serializers.CharField(
        source="user.username",
        read_only=True
    )

    full_name = serializers.SerializerMethodField()

    class Meta:

        model = CoachProfile

        fields = [
            "id",
            "user",
            "username",
            "full_name",
            "headline",
            "biography",
            "specialization",
            "experience_level",
            "years_of_experience",
            "sport",
            "country",
            "city",
            "organization",
            "profile_photo",
            "cover_photo",
            "certifications",
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
# COACH TALENT VIEW
# ============================================================

class CoachTalentViewSerializer(serializers.ModelSerializer):

    talent_name = serializers.SerializerMethodField()

    class Meta:

        model = CoachTalentView

        fields = [
            "id",
            "coach",
            "talent",
            "talent_name",
            "viewed_at",
        ]

        read_only_fields = [
            "id",
            "coach",
            "viewed_at",
        ]

    def get_talent_name(self, obj):

        return (
            obj.talent.user.get_full_name()
            or obj.talent.user.username
        )


# ============================================================
# COACH TALENT FOLLOW
# ============================================================

class CoachTalentFollowSerializer(serializers.ModelSerializer):

    talent_name = serializers.SerializerMethodField()

    class Meta:

        model = CoachTalentFollow

        fields = [
            "id",
            "coach",
            "talent",
            "talent_name",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "coach",
            "created_at",
        ]

    def get_talent_name(self, obj):

        return (
            obj.talent.user.get_full_name()
            or obj.talent.user.username
        )


# ============================================================
# COACH TALENT BOOKMARK
# ============================================================

class CoachTalentBookmarkSerializer(serializers.ModelSerializer):

    talent_name = serializers.SerializerMethodField()

    class Meta:

        model = CoachTalentBookmark

        fields = [
            "id",
            "coach",
            "talent",
            "talent_name",
            "notes",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "coach",
            "created_at",
            "updated_at",
        ]

    def get_talent_name(self, obj):

        return (
            obj.talent.user.get_full_name()
            or obj.talent.user.username
        )
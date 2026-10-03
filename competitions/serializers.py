from rest_framework import serializers

from .models import (
    Competition,
    CompetitionEvaluation,
    CompetitionJudge,
    CompetitionParticipant,
    CompetitionResult,
)


class CompetitionSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(
        source="organization.name",
        read_only=True,
    )
    participant_count = serializers.IntegerField(read_only=True)
    registration_open = serializers.BooleanField(read_only=True)

    class Meta:
        model = Competition
        fields = (
            "id",
            "organization",
            "organization_name",
            "title",
            "description",
            "category",
            "discipline",
            "status",
            "registration_start",
            "registration_end",
            "competition_start",
            "competition_end",
            "location",
            "online",
            "requirements",
            "prizes",
            "rules",
            "max_participants",
            "review_note",
            "participant_count",
            "registration_open",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "organization",
            "organization_name",
            "status",
            "review_note",
            "participant_count",
            "registration_open",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        current = self.instance
        registration_start = attrs.get(
            "registration_start",
            getattr(current, "registration_start", None),
        )
        registration_end = attrs.get(
            "registration_end",
            getattr(current, "registration_end", None),
        )
        competition_start = attrs.get(
            "competition_start",
            getattr(current, "competition_start", None),
        )
        competition_end = attrs.get(
            "competition_end",
            getattr(current, "competition_end", None),
        )
        errors = {}
        if (
            registration_start
            and registration_end
            and registration_end < registration_start
        ):
            errors["registration_end"] = "Must be on or after registration start."
        if (
            competition_start
            and competition_end
            and competition_end < competition_start
        ):
            errors["competition_end"] = "Must be on or after competition start."
        if (
            registration_end
            and competition_start
            and competition_start < registration_end
        ):
            errors["competition_start"] = "Must be on or after registration end."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class CompetitionParticipantSerializer(serializers.ModelSerializer):
    talent = serializers.SerializerMethodField()
    competition_title = serializers.CharField(
        source="competition.title",
        read_only=True,
    )

    class Meta:
        model = CompetitionParticipant
        fields = (
            "id",
            "competition",
            "competition_title",
            "talent",
            "status",
            "submission",
            "submission_url",
            "submitted_at",
            "registered_at",
        )
        read_only_fields = fields

    def get_talent(self, participant):
        talent = participant.talent
        return {
            "id": talent.pk,
            "name": talent.user.get_full_name() or talent.user.username,
            "category": talent.get_talent_category_display(),
        }


class PublicCompetitionParticipantSerializer(serializers.ModelSerializer):
    talent = serializers.SerializerMethodField()

    class Meta:
        model = CompetitionParticipant
        fields = ("id", "talent", "registered_at")
        read_only_fields = fields

    def get_talent(self, participant):
        talent = participant.talent
        return {
            "id": talent.pk,
            "name": talent.user.get_full_name() or talent.user.username,
            "category": talent.get_talent_category_display(),
        }


class CompetitionSubmissionSerializer(serializers.Serializer):
    submission = serializers.CharField(
        allow_blank=True,
        required=False,
    )
    submission_url = serializers.URLField(
        allow_blank=True,
        required=False,
    )


class CompetitionJudgeSerializer(serializers.ModelSerializer):
    coach_name = serializers.SerializerMethodField()

    class Meta:
        model = CompetitionJudge
        fields = ("id", "competition", "coach", "coach_name", "role", "assigned_at")
        read_only_fields = fields

    def get_coach_name(self, assignment):
        return assignment.coach.get_full_name() or assignment.coach.username


class CompetitionEvaluationSerializer(serializers.ModelSerializer):
    score = serializers.DecimalField(
        max_digits=6,
        decimal_places=2,
        min_value=0,
        max_value=100,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = CompetitionEvaluation
        fields = ("id", "participant", "judge", "score", "feedback", "updated_at")
        read_only_fields = ("id", "participant", "judge", "updated_at")

    def validate(self, attrs):
        attrs = super().validate(attrs)
        requires_score = self.context.get("requires_score", True)
        instance = self.instance
        score = attrs.get("score", getattr(instance, "score", None))
        feedback = attrs.get(
            "feedback",
            getattr(instance, "feedback", ""),
        ).strip()
        if requires_score and score is None:
            raise serializers.ValidationError(
                {"score": "A score is required for judging and evaluation."}
            )
        if not requires_score and not feedback:
            raise serializers.ValidationError(
                {"feedback": "Enter feedback before saving a mentoring note."}
            )
        return attrs


class CompetitionResultSerializer(serializers.ModelSerializer):
    participant = serializers.SerializerMethodField()
    position = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
    )

    class Meta:
        model = CompetitionResult
        fields = ("id", "participant", "position", "score", "award", "published_at")
        read_only_fields = ("id", "participant", "published_at")

    def validate(self, attrs):
        attrs = super().validate(attrs)
        instance = self.instance
        position = attrs.get("position", getattr(instance, "position", None))
        score = attrs.get("score", getattr(instance, "score", None))
        award = attrs.get("award", getattr(instance, "award", "")).strip()
        if position is None and score is None and not award:
            raise serializers.ValidationError(
                "Enter a position, score, or award for this participant."
            )
        return attrs

    def get_participant(self, result):
        participant = result.participant
        talent = participant.talent
        return {
            "id": participant.pk,
            "talent": {
                "id": talent.pk,
                "name": talent.user.get_full_name() or talent.user.username,
            },
        }

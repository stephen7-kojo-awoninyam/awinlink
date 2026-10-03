from django.contrib import admin

from .models import (
    Competition,
    CompetitionEvaluation,
    CompetitionJudge,
    CompetitionParticipant,
    CompetitionResult,
)


class CompetitionParticipantInline(admin.TabularInline):
    model = CompetitionParticipant
    extra = 0
    readonly_fields = ("registered_at", "submitted_at")


class CompetitionJudgeInline(admin.TabularInline):
    model = CompetitionJudge
    extra = 0
    readonly_fields = ("assigned_at",)


@admin.register(Competition)
class CompetitionAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "organization",
        "category",
        "status",
        "registration_start",
        "registration_end",
        "competition_start",
    )
    list_filter = ("status", "category", "online")
    search_fields = ("title", "organization__name", "discipline")
    readonly_fields = ("created_at", "updated_at")
    inlines = (CompetitionParticipantInline, CompetitionJudgeInline)


@admin.register(CompetitionParticipant)
class CompetitionParticipantAdmin(admin.ModelAdmin):
    list_display = ("competition", "talent", "status", "registered_at")
    list_filter = ("status", "competition__category")
    search_fields = ("competition__title", "talent__user__username")
    readonly_fields = ("registered_at", "submitted_at")


@admin.register(CompetitionJudge)
class CompetitionJudgeAdmin(admin.ModelAdmin):
    list_display = ("competition", "coach", "role", "assigned_at")
    list_filter = ("role",)
    search_fields = ("competition__title", "coach__username")
    readonly_fields = ("assigned_at",)


@admin.register(CompetitionEvaluation)
class CompetitionEvaluationAdmin(admin.ModelAdmin):
    list_display = ("participant", "judge", "score", "updated_at")
    search_fields = ("participant__competition__title", "judge__username")
    readonly_fields = ("updated_at",)


@admin.register(CompetitionResult)
class CompetitionResultAdmin(admin.ModelAdmin):
    list_display = ("participant", "position", "score", "award", "published_at")
    search_fields = ("participant__competition__title", "award")
    readonly_fields = ("published_at",)

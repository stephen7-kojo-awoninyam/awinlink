from django.contrib import admin

# Register your models here.

from django.contrib import admin

from .models import Shortlist


@admin.register(Shortlist)
class ShortlistAdmin(admin.ModelAdmin):

    list_display = (
        "organization",
        "talent",
        "starred",
        "created_at",
        "updated_at",
    )

    list_filter = (
        "starred",
        "organization",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "organization__name",
        "talent__user__first_name",
        "talent__user__last_name",
        "talent__headline",
        "notes",
    )

    autocomplete_fields = (
        "organization",
        "talent",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    ordering = (
        "-created_at",
    )

    fieldsets = (
        (
            "Shortlist Information",
            {
                "fields": (
                    "organization",
                    "talent",
                )
            },
        ),
        (
            "Recruiter Notes",
            {
                "fields": (
                    "notes",
                    "starred",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )
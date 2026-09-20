from django.contrib import admin

from .models import (
    Sport,
    SportCategory,
    PerformanceMetric,
)


@admin.register(Sport)
class SportAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "created_at",
    )

    search_fields = (
        "name",
    )

    ordering = (
        "name",
    )


@admin.register(SportCategory)
class SportCategoryAdmin(admin.ModelAdmin):

    list_display = (
        "sport",
        "name",
    )

    search_fields = (
        "sport__name",
        "name",
    )

    list_filter = (
        "sport",
    )

    ordering = (
        "sport__name",
        "name",
    )


@admin.register(PerformanceMetric)
class PerformanceMetricAdmin(admin.ModelAdmin):

    list_display = (
        "sport",
        "name",
        "unit",
    )

    search_fields = (
        "sport__name",
        "name",
    )

    list_filter = (
        "sport",
    )

    ordering = (
        "sport__name",
        "name",
    )
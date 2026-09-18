from django.contrib import admin
from .models import Sport, SportCategory, PerformanceMetric
# Register your models here.

@admin.register(Sport)
class SportAdmin(admin.ModelAdmin):

    list_display = (
        "name",
    )


@admin.register(SportCategory)
class SportCategoryAdmin(admin.ModelAdmin):

    list_display = (
        "sport",
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
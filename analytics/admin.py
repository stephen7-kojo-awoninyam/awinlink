from django.contrib import admin
from .models import RecommendationHistory   
# Register your models here.


@admin.register(RecommendationHistory)
class RecommendationHistoryAdmin(admin.ModelAdmin):


    list_display = (

        "organization",
        "talent",
        "opportunity",
        "score",
        "created_at",

    )


    list_filter = (

        "organization",
        "score",
        "created_at",

    )


    search_fields = (

        "organization__name",
        "talent__user__username",
        "talent__user__first_name",
        "talent__user__last_name",

    )
from django.contrib import admin
from .models import AthleteProfile
from .models import (
    AthleteProfile,
    Achievement,
    AthleteMedia
)
# Register your models here.

@admin.register(AthleteProfile)
class AthleteProfileAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "sport",
        "category",
        "current_team",
    )

    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "sport__name",
        "category__name",
    )
    

admin.site.register(Achievement)
@admin.register(AthleteMedia)
class AthleteMediaAdmin(admin.ModelAdmin):

    list_display = (
        "athlete",
        "title",
        "media_type",
        "uploaded_at",
    )

    list_filter = (
        "media_type",
    ) 
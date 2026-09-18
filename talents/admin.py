from django.contrib import admin
from .models import TalentProfile,  VerificationRequest
from .models import Achievement, Certification,Experience
# Register your models here.

@admin.register(TalentProfile)
class TalentProfileAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "headline",
        "country",
        "verified",
        "created_at",
    )

    list_filter = (
        "verified",
        "country",
    )

    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "user__email",
        "headline",
        "country",
        "city",
    )

@admin.register(VerificationRequest)
class VerificationRequestAdmin(admin.ModelAdmin):

    list_display = (
        "talent",
        "status",
        "created_at"
    )


    list_filter = (
        "status",
    ) 
@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):

    list_display = (
        "talent",
        "title",
        "date_received",
    )



@admin.register(Certification)
class CertificationAdmin(admin.ModelAdmin):

    list_display = (
        "talent",
        "name",
        "issuing_organization",
    )  
    
@admin.register(Experience)
class ExperienceAdmin(admin.ModelAdmin):

    list_display = (
        "talent",
        "role",
        "company",
        "start_date",
        "currently_working",
    )         
    
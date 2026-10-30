from django.contrib import admin
from .models import TalentProfile,  VerificationRequest
from .models import Achievement, Certification,Experience
from .verification_permissions import verification_reviewer
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

    def has_module_permission(self, request):
        return verification_reviewer(request.user) and super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        return verification_reviewer(request.user) and super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return verification_reviewer(request.user) and super().has_change_permission(request, obj)

    def has_add_permission(self, request):
        return verification_reviewer(request.user) and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return verification_reviewer(request.user) and super().has_delete_permission(request, obj)

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

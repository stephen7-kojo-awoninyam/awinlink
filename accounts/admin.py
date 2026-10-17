from django.contrib import admin
from .models import ContentReport, UserBlock


@admin.register(ContentReport)
class ContentReportAdmin(admin.ModelAdmin):
    list_display = ['id', 'target_type', 'target_id', 'reason', 'status', 'created_at']
    list_filter = ['status', 'reason', 'target_type']
    readonly_fields = ['reporter', 'target_type', 'target_id', 'reason', 'details', 'created_at']
    search_fields = ['details']


@admin.register(UserBlock)
class UserBlockAdmin(admin.ModelAdmin):
    list_display = ['user', 'blocked_user', 'created_at']

# Register your models here.

from django.contrib import admin
from .models import EventCertificate, EventMedia

# Register your models here.

from .models import (
    EventCategory,
    Event,
    EventRegistration,
    EventFeedback
)



@admin.register(EventCategory)
class EventCategoryAdmin(admin.ModelAdmin):

    list_display = (
        "name",
    )

    search_fields = (
        "name",
    )



@admin.register(Event)
class EventAdmin(admin.ModelAdmin):

    list_display = (
        "title",
        "organizer",
        "category",
        "event_type",
        "status",
        "start_date",
        "created_at",
    )


    list_filter = (
        "event_type",
        "status",
        "category",
        "online",
    )


    search_fields = (
        "title",
        "description",
    )


    prepopulated_fields = {
        "slug":(
            "title",
        )
    }

    def save_model(self, request, obj, form, change):
        if change:
            from media_erasure.services import save_instance_with_media_retention
            save_instance_with_media_retention(obj,
                lambda: super(EventAdmin, self).save_model(request, obj, form, change),
                requested_by_id=request.user.pk)
            return
        super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        from media_erasure.services import delete_event_with_retention
        delete_event_with_retention(obj, requested_by_id=request.user.pk)

    def delete_queryset(self, request, queryset):
        from django.db import transaction
        from media_erasure.services import delete_event_with_retention
        with transaction.atomic():
            for obj in queryset.select_for_update().order_by('pk'):
                delete_event_with_retention(obj, requested_by_id=request.user.pk)



@admin.register(EventRegistration)
class EventRegistrationAdmin(admin.ModelAdmin):

    list_display = (
        "event",
        "talent",
        "status",
        "registered_at",
    )


    list_filter = (
        "status",
    )



@admin.register(EventFeedback)
class EventFeedbackAdmin(admin.ModelAdmin):

    list_display = (
        "event",
        "reviewer",
        "rating",
        "created_at",
    )


    list_filter = (
        "rating",
    )


@admin.register(EventMedia)
class EventMediaAdmin(admin.ModelAdmin):
    list_display = ('event', 'uploaded_by', 'media_type', 'uploaded_at')
    readonly_fields = ('event', 'uploaded_by', 'media_type', 'file', 'caption', 'uploaded_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def delete_model(self, request, obj):
        from media_erasure.services import delete_instance_with_retention
        delete_instance_with_retention(obj, requested_by_id=request.user.pk)

    def delete_queryset(self, request, queryset):
        from django.db import transaction
        from media_erasure.services import delete_instance_with_retention
        with transaction.atomic():
            for obj in queryset.select_for_update().order_by('pk'):
                delete_instance_with_retention(obj, requested_by_id=request.user.pk)
    
    
@admin.register(EventCertificate)
class EventCertificateAdmin(admin.ModelAdmin):

    list_display = (

        "event",
        "talent",
        "certificate_title",
        "certificate_code",
        "issued_by",
        "issued_at",

    )


    search_fields = (

        "certificate_code",
        "talent__user__username",
        "event__title",

    )


    list_filter = (

        "issued_at",

    )


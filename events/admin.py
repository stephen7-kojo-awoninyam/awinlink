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
    
    
   
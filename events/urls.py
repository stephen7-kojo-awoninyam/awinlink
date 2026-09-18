from django.urls import path

from . import views


urlpatterns = [

    # ==========================================
    # EVENT DISCOVERY
    # ==========================================

    path(
        "",
        views.event_list,
        name="event_list"
    ),

    path(
        "recommended/",
        views.recommended_events,
        name="recommended_events"
    ),

    path(
        "my-events/",
        views.my_events,
        name="my_events"
    ),

  
    # ==========================================
    # EVENT CREATION
    # ==========================================

    path(
        "create/",
        views.create_event,
        name="create_event"
    ),

    # ==========================================
    # ORGANIZATION EVENTS
    # ==========================================

    path(
        "organization/",
        views.organization_events,
        name="organization_events"
    ),

    path(
        "analytics/",
        views.event_analytics,
        name="event_analytics"
    ),

    # ==========================================
    # EVENT REGISTRATION
    # ==========================================

    path(
        "<int:event_id>/register/",
        views.register_event,
        name="register_event"
    ),

    path(
        "<int:event_id>/cancel/",
        views.cancel_registration,
        name="cancel_registration"
    ),

    # ==========================================
    # PARTICIPANTS
    # ==========================================

    path(
        "<int:event_id>/participants/",
        views.event_participants,
        name="event_participants"
    ),

    path(
        "registration/<int:registration_id>/approve/",
        views.approve_registration,
        name="approve_registration"
    ),

    path(
        "registration/<int:registration_id>/reject/",
        views.reject_registration,
        name="reject_registration"
    ),

    path(
        "registration/<int:registration_id>/attendance/",
        views.mark_attendance,
        name="mark_attendance"
    ),

    # ==========================================
    # EVENT FEEDBACK
    # ==========================================

    path(
        "<int:event_id>/feedback/",
        views.give_feedback,
        name="give_feedback"
    ),

    # ==========================================
    # EVENT DASHBOARD
    # ==========================================

    path(
        "organization/event/<int:event_id>/dashboard/",
        views.event_dashboard,
        name="event_dashboard"
    ),

    # ==========================================
    # CERTIFICATES
    # ==========================================
    
    
    path(
        "my-certificates/",
        views.my_certificates,
        name="my_certificates"
    ),
    
    path(
    "certificate/<int:certificate_id>/",
    views.certificate_detail,
    name="certificate_detail"
    ),

    path(
        "certificates/",
        views.talent_certificates,
        name="talent_certificates"
    ),

    path(
        "verify/<str:certificate_code>/",
        views.verify_certificate,
        name="verify_certificate"
    ),

    # ==========================================
    # EVENT GALLERY
    # ==========================================

    path(
        "<int:event_id>/gallery/",
        views.event_gallery,
        name="event_gallery"
    ),

    path(
        "<int:event_id>/gallery/upload/",
        views.upload_event_media,
        name="upload_event_media"
    ),

    path(
        "gallery/delete/<int:media_id>/",
        views.delete_event_media,
        name="delete_event_media"
    ),

    # ==========================================
    # EVENT DETAIL
    # ==========================================

    path(
        "<int:event_id>/",
        views.event_detail,
        name="event_detail"
    ),
]
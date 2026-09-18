from django.urls import path

from .api_views import (
    EventCategoryListAPIView,
    EventListAPIView,
    EventDetailAPIView,
    EventCreateAPIView,
    EventUpdateAPIView,
    EventDeleteAPIView,
    EventRegisterAPIView,
    EventCancelRegistrationAPIView,
    MyEventRegistrationsAPIView,
    EventRegistrationListAPIView,
    EventRegistrationStatusAPIView,
    EventAttendanceAPIView,
    EventFeedbackCreateAPIView,
    EventFeedbackListAPIView,
    MyEventCertificatesAPIView,
    EventCertificateVerifyAPIView,
    EventMediaListAPIView,
    EventMediaCreateAPIView,
)


app_name = "events_api"


urlpatterns = [

    # =====================================================
    # EVENT CATEGORIES
    # =====================================================

    path(
        "categories/",
        EventCategoryListAPIView.as_view(),
        name="event_categories",
    ),


    # =====================================================
    # EVENTS
    # =====================================================

    path(
        "",
        EventListAPIView.as_view(),
        name="event_list",
    ),

    path(
        "create/",
        EventCreateAPIView.as_view(),
        name="event_create",
    ),

    path(
        "<int:event_id>/",
        EventDetailAPIView.as_view(),
        name="event_detail",
    ),

    path(
        "<int:event_id>/update/",
        EventUpdateAPIView.as_view(),
        name="event_update",
    ),

    path(
        "<int:event_id>/delete/",
        EventDeleteAPIView.as_view(),
        name="event_delete",
    ),


    # =====================================================
    # EVENT REGISTRATION
    # =====================================================

    path(
        "<int:event_id>/register/",
        EventRegisterAPIView.as_view(),
        name="event_register",
    ),

    path(
        "<int:event_id>/cancel-registration/",
        EventCancelRegistrationAPIView.as_view(),
        name="event_cancel_registration",
    ),

    path(
        "my-registrations/",
        MyEventRegistrationsAPIView.as_view(),
        name="my_event_registrations",
    ),

    path(
        "registrations/",
        EventRegistrationListAPIView.as_view(),
        name="event_registrations",
    ),

    path(
        "registrations/<int:registration_id>/status/",
        EventRegistrationStatusAPIView.as_view(),
        name="event_registration_status",
    ),

    path(
        "registrations/<int:registration_id>/attendance/",
        EventAttendanceAPIView.as_view(),
        name="event_attendance",
    ),


    # =====================================================
    # EVENT FEEDBACK
    # =====================================================

    path(
        "<int:event_id>/feedback/",
        EventFeedbackCreateAPIView.as_view(),
        name="event_feedback_create",
    ),

    path(
        "<int:event_id>/feedback/list/",
        EventFeedbackListAPIView.as_view(),
        name="event_feedback_list",
    ),


    # =====================================================
    # EVENT CERTIFICATES
    # =====================================================

    path(
        "my-certificates/",
        MyEventCertificatesAPIView.as_view(),
        name="my_event_certificates",
    ),

    path(
        "certificates/<str:certificate_code>/verify/",
        EventCertificateVerifyAPIView.as_view(),
        name="event_certificate_verify",
    ),


    # =====================================================
    # EVENT MEDIA
    # =====================================================

    path(
        "<int:event_id>/media/",
        EventMediaListAPIView.as_view(),
        name="event_media",
    ),

    path(
        "<int:event_id>/media/upload/",
        EventMediaCreateAPIView.as_view(),
        name="event_media_upload",
    ),

]
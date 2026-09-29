from django.urls import path
from . import views



urlpatterns = [

    path(
        "read-all/",
        views.mark_all_notifications_read,
        name="mark_all_notifications_read"
    ),

    path(
        "push/config/",
        views.push_config,
        name="push_config"
    ),

    path(
        "push/subscriptions/",
        views.manage_push_subscription,
        name="manage_push_subscription"
    ),


    path(
        "",
        views.notification_list,
        name="notification_list"
    ),



    path(
        "<int:notification_id>/",
        views.notification_detail,
        name="notification_detail"
    ),
    
    path(
        "read/<int:notification_id>/",
        views.mark_notification_read,
        name="mark_notification_read"
    ),



]
from django.urls import path

from . import views


app_name = "messaging"


urlpatterns = [

    # =====================================================
    # WEB MESSAGING
    # =====================================================

    path(
        "conversations/",
        views.conversation_list,
        name="conversation_list",
    ),

    path(
        "<int:conversation_id>/",
        views.conversation,
        name="conversation",
    ),

    path(
        "<int:conversation_id>/send/",
        views.send_message,
        name="send_message",
    ),

    path(
        "start/<int:user_id>/",
        views.start_conversation,
        name="start_conversation",
    ),

    path(
        "start/<int:user_id>/<int:opportunity_id>/",
        views.start_conversation,
        name="start_conversation_with_opportunity",
    ),

]
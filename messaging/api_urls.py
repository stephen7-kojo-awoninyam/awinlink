from django.urls import path

from .api_views import (
    MyConversationsAPIView,
    ConversationCreateAPIView,
    ConversationDetailAPIView,
    ConversationMessagesAPIView,
    SendMessageAPIView,
    MessageReadAPIView,
    ConversationReadAllAPIView,
    StartCallAPIView,
    AcceptCallAPIView,
    RejectCallAPIView,
    EndCallAPIView,
    IncomingCallsAPIView,
    AddGroupMemberAPIView,
    RemoveGroupMemberAPIView,
)


app_name = "messaging_api"


urlpatterns = [

    # =====================================================
    # CONVERSATIONS
    # =====================================================

    path(
        "conversations/",
        MyConversationsAPIView.as_view(),
        name="my_conversations",
    ),

    path(
        "conversations/create/",
        ConversationCreateAPIView.as_view(),
        name="conversation_create",
    ),

    path(
        "conversations/<int:conversation_id>/calls/start/",
        StartCallAPIView.as_view(),
        name="call_start",
    ),

    path(
        "conversations/<int:conversation_id>/messages/",
        ConversationMessagesAPIView.as_view(),
        name="conversation_messages",
    ),

    path(
        "conversations/<int:conversation_id>/messages/create/",
        SendMessageAPIView.as_view(),
        name="send_message",
    ),

    path(
        "conversations/<int:conversation_id>/read-all/",
        ConversationReadAllAPIView.as_view(),
        name="conversation_read_all",
    ),

    path(
        "conversations/<int:conversation_id>/",
        ConversationDetailAPIView.as_view(),
        name="conversation_detail",
    ),
    
    path(
    "conversations/<int:conversation_id>/members/add/",
    AddGroupMemberAPIView.as_view(),
    name="group_member_add",
    ),

    path(
        "conversations/<int:conversation_id>/members/<int:user_id>/remove/",
        RemoveGroupMemberAPIView.as_view(),
        name="group_member_remove",
    ),



    # =====================================================
    # MESSAGES
    # =====================================================

    path(
        "messages/<int:message_id>/read/",
        MessageReadAPIView.as_view(),
        name="message_read",
    ),


    path(
        "calls/<int:call_id>/accept/",
        AcceptCallAPIView.as_view(),
        name="call_accept",
    ),

    path(
        "calls/<int:call_id>/reject/",
        RejectCallAPIView.as_view(),
        name="call_reject",
    ),

    path(
        "calls/<int:call_id>/end/",
        EndCallAPIView.as_view(),
        name="call_end",
    ),
    path(
    "calls/incoming/",
    IncomingCallsAPIView.as_view(),
    name="incoming_calls"
    ),

]

from django.urls import path

from . import views



urlpatterns = [


    # USER FOLLOW

    path(

        "follow/user/<int:user_id>/",

        views.follow_user,

        name="follow_user"

    ),



    path(

        "unfollow/user/<int:user_id>/",

        views.unfollow_user,

        name="unfollow_user"

    ),





    # ORGANIZATION FOLLOW


    path(

        "follow/organization/<int:organization_id>/",

        views.follow_organization,

        name="follow_organization"

    ),



    path(

        "unfollow/organization/<int:organization_id>/",

        views.unfollow_organization,

        name="unfollow_organization"

    ),
    
    
    # ==========================================
    # PROFESSIONAL CONNECTIONS
    # ==========================================

    path(
        "connect/<int:user_id>/",
        views.send_connection_request,
        name="send_connection_request"
    ),

    path(
        "connection/<int:connection_id>/accept/",
        views.accept_connection_request,
        name="accept_connection_request"
    ),

    path(
        "connection/<int:connection_id>/reject/",
        views.reject_connection_request,
        name="reject_connection_request"
    ),
    path(
        "connect/cancel/<int:connection_id>/",
        views.cancel_connection_request,
        name="cancel_connection_request"
    ),
    
    path(
        "connections/",
        views.connections_list,
        name="connections_list"
    ),
    path(
    "groups/create/",
    views.create_group,
    name="create_group"
    ),
    
    path(
    "connection/<int:connection_id>/remove/",
    views.remove_connection,
    name="remove_connection"
    ),

]
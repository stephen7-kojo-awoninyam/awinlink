from django.urls import path
from . import views

from django.urls import path
from . import views


urlpatterns = [

    path(
        "invite/<int:opportunity_id>/<int:talent_id>/",
        views.invite_talent,
        name="invite_talent"
    ),


    path(
        "accept/<int:invitation_id>/",
        views.accept_invitation,
        name="accept_invitation"
    ),


    path(
        "decline/<int:invitation_id>/",
        views.decline_invitation,
        name="decline_invitation"
    ),

]
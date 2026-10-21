from django.urls import path
from . import views

from django.urls import path
from . import views


urlpatterns = [

    path("invite/talent/<int:talent_id>/", views.invite_talent, name="invite_talent_profile"),

    path(
        "invite/<int:opportunity_id>/<int:talent_id>/",
        views.invite_talent_for_opportunity,
        name="invite_talent_for_opportunity"
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

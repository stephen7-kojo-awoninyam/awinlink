from django.urls import path

from . import views


urlpatterns = [

    path(
        "profile/setup/",
        views.sports_profile_setup,
        name="sports_profile_setup"
    ),

]
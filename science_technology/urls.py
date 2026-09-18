from django.urls import path

from . import views


urlpatterns = [

    path(
        "profile-setup/",
        views.science_technology_profile_setup,
        name="technology_profile_setup"
    ),

]

from django.urls import path

from . import views


urlpatterns = [

    path(
        "profile-setup/",
        views.other_profile_setup,
        name="other_profile_setup"
    ),

]


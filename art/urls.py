
from django.urls import path

from . import views


urlpatterns = [

    path(
        "profile-setup/",
        views.arts_profile_setup,
        name="arts_profile_setup"
    ),

]


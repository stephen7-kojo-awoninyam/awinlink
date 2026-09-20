from django.urls import path
from . import views


urlpatterns = [

    path(
        "create/",
        views.create_profile,
        name="create_profile"
    ),
    path(
    "<int:id>/",
    views.athlete_profile,
    name="athlete_profile"
),
    path(
    "media/add/",
    views.add_media,
    name="add_media"
),   
    

]
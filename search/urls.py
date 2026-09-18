from django.urls import path
from . import views


urlpatterns = [

    path(
        "",
        views.talent_search,
        name="talent_search"
    ),
    
    path(
        "opportunities/",
        views.opportunity_search,
        name="opportunity_search"
    ),


]
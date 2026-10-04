from django.urls import path
from . import views


urlpatterns = [
    path(
        "username-suggestions/",
        views.username_suggestions,
        name="username_suggestions",
    ),

    path(
        "",
        views.talent_search,
        name="user_search"
    ),

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
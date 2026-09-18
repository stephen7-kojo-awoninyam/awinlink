from django.urls import path

from . import views

app_name = "analytics"

urlpatterns = [

    path(
        "talent/",
        views.talent_analytics,
        name="talent_analytics"
    ),
    
    path(
        "organization/",
        views.organization_analytics,
        name="organization_analytics"
    ),
    path(
        "admin/",
        views.admin_analytics,
        name="admin_analytics"
    ),
    
    path(
        "",
        views.analytics_dashboard,
        name="analytics_dashboard"
    ),
    path(
        "coach/",
        views.coach_analytics,
        name="coach_analytics"
    ),
    
    path(
        "scout/",
        views.scout_analytics,
        name="scout_analytics"
    ),

]
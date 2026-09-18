from django.urls import path
from . import views


urlpatterns = [

    path(
        "dashboard/",
        views.organization_dashboard,
        name="organization_dashboard"
    ),
path(
    "applications/",
    views.organization_applications,
    name="organization_applications"
),
path(
        "edit-profile/",
        views.edit_organization_profile,
        name="edit_organization_profile"
    ),

path(
    "profile/<int:organization_id>/",
    views.organization_profile,
    name="organization_profile"
),
path(
    "opportunity/<int:opportunity_id>/recommendations/",
    views.opportunity_recommendations,
    name="opportunity_recommendations"
),

path(
    "invite-talent/<int:talent_id>/<int:opportunity_id>/",
    views.invite_talent,
    name="invite_talent"
),
path(
    "talent-search/",
    views.talent_search,
    name="talent_search"
),
path(
    "shortlisted/",
    views.shortlisted_talents,
    name="shortlisted_talents"
),
path(
    "directory/",
    views.organization_directory,
    name="organization_directory"
),
path(
    "",
    views.organization_list,
    name="organization_list"
),

path(
    "profile/<int:organization_id>/follow/",
    views.follow_organization,
    name="follow_organization"
),

path(
    "profile/<int:organization_id>/unfollow/",
    views.unfollow_organization,
    name="unfollow_organization"
),
]
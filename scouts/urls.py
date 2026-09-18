from django.urls import path

from . import views


urlpatterns = [

    # Scout dashboard

    path(
        "",
        views.scout_dashboard,
        name="scout_dashboard"
    ),

    # Talent discovery

    path(
        "talents/",
        views.scout_talent_list,
        name="scout_talent_list"
    ),

    # Talent profile

    path(
        "talents/<int:talent_id>/",
        views.scout_talent_detail,
        name="scout_talent_detail"
    ),

    # Follow

    path(
        "talents/<int:talent_id>/follow/",
        views.follow_talent,
        name="follow_talent"
    ),

    # Bookmark

    path(
        "talents/<int:talent_id>/bookmark/",
        views.bookmark_talent,
        name="bookmark_talent"
    ),
    
    path(
        "talent/<int:talent_id>/remove-bookmark/",
        views.remove_bookmark,
        name="remove_bookmark"
    ),
    path(
        "saved-talents/",
        views.saved_talents,
        name="saved_talents"
    ),
    
    path(
        "talents/",
        views.scout_talent_list,
        name="scout_talent_list"
    ),
    path(
        "bookmarks/",
        views.scout_bookmarked_talents,
        name="scout_bookmarked_talents"
    ),
    path(
        "following/",
        views.scout_followed_talents,
        name="scout_followed_talents"
    ),
    
    path(
    "talent/<int:talent_id>/notes/",
    views.update_bookmark_notes,
    name="update_bookmark_notes"
    ),
]
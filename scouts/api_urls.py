from django.urls import path

from .api_views import (
    MyScoutProfileAPIView,
    MyScoutProfileUpdateAPIView,
    ScoutTalentListAPIView,
    ScoutViewTalentAPIView,
    MyScoutTalentViewsAPIView,
    ScoutFollowTalentAPIView,
    ScoutUnfollowTalentAPIView,
    MyFollowedTalentsAPIView,
    ScoutBookmarkTalentAPIView,
    ScoutBookmarkUpdateAPIView,
    ScoutBookmarkDeleteAPIView,
    MyScoutBookmarksAPIView,
)


app_name = "scouts_api"


urlpatterns = [

    # =====================================================
    # SCOUT PROFILE
    # =====================================================

    path(
        "profile/",
        MyScoutProfileAPIView.as_view(),
        name="my_scout_profile"
    ),

    path(
        "profile/update/",
        MyScoutProfileUpdateAPIView.as_view(),
        name="my_scout_profile_update"
    ),

    # =====================================================
    # TALENT VIEWS
    # =====================================================

    path(
        "talents/views/",
        MyScoutTalentViewsAPIView.as_view(),
        name="my_talent_views"
    ),

    path(
        "talents/<int:talent_id>/view/",
        ScoutViewTalentAPIView.as_view(),
        name="view_talent"
    ),

    # =====================================================
    # TALENT FOLLOWS
    # =====================================================

    path(
        "talents/following/",
        MyFollowedTalentsAPIView.as_view(),
        name="followed_talents"
    ),

    path(
        "talents/<int:talent_id>/follow/",
        ScoutFollowTalentAPIView.as_view(),
        name="follow_talent"
    ),

    path(
        "talents/<int:talent_id>/unfollow/",
        ScoutUnfollowTalentAPIView.as_view(),
        name="unfollow_talent"
    ),
    path(
    "talents/",
    ScoutTalentListAPIView.as_view(),
    name="scout_talent_list"
    ),

    # =====================================================
    # TALENT BOOKMARKS
    # =====================================================

    path(
        "talents/bookmarks/",
        MyScoutBookmarksAPIView.as_view(),
        name="my_bookmarks"
    ),

    path(
        "talents/<int:talent_id>/bookmark/",
        ScoutBookmarkTalentAPIView.as_view(),
        name="bookmark_talent"
    ),

    path(
        "bookmarks/<int:bookmark_id>/update/",
        ScoutBookmarkUpdateAPIView.as_view(),
        name="bookmark_update"
    ),

    path(
        "bookmarks/<int:bookmark_id>/delete/",
        ScoutBookmarkDeleteAPIView.as_view(),
        name="bookmark_delete"
    ),

]
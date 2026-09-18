from django.urls import path

from .api_views import (
    MyCoachProfileAPIView,
    MyCoachProfileUpdateAPIView,
    CoachTalentListAPIView,
    CoachViewTalentAPIView,
    MyCoachTalentViewsAPIView,
    CoachFollowTalentAPIView,
    CoachUnfollowTalentAPIView,
    MyFollowedTalentsAPIView,
    CoachBookmarkTalentAPIView,
    CoachBookmarkUpdateAPIView,
    CoachBookmarkDeleteAPIView,
    MyCoachBookmarksAPIView,
)


app_name = "coaches_api"


urlpatterns = [

    # =====================================================
    # COACH PROFILE
    # =====================================================

    path(
        "profile/",
        MyCoachProfileAPIView.as_view(),
        name="my_coach_profile"
    ),

    path(
        "profile/update/",
        MyCoachProfileUpdateAPIView.as_view(),
        name="my_coach_profile_update"
    ),

    # =====================================================
    # TALENT DISCOVERY
    # =====================================================

    path(
        "talents/",
        CoachTalentListAPIView.as_view(),
        name="coach_talent_list"
    ),

    # =====================================================
    # TALENT VIEWS
    # =====================================================

    path(
        "talents/views/",
        MyCoachTalentViewsAPIView.as_view(),
        name="my_talent_views"
    ),

    path(
        "talents/<int:talent_id>/view/",
        CoachViewTalentAPIView.as_view(),
        name="view_talent"
    ),

    # =====================================================
    # TALENT FOLLOWING
    # =====================================================

    path(
        "talents/following/",
        MyFollowedTalentsAPIView.as_view(),
        name="followed_talents"
    ),

    path(
        "talents/<int:talent_id>/follow/",
        CoachFollowTalentAPIView.as_view(),
        name="follow_talent"
    ),

    path(
        "talents/<int:talent_id>/unfollow/",
        CoachUnfollowTalentAPIView.as_view(),
        name="unfollow_talent"
    ),

    # =====================================================
    # TALENT BOOKMARKS
    # =====================================================

    path(
        "talents/bookmarks/",
        MyCoachBookmarksAPIView.as_view(),
        name="my_bookmarks"
    ),

    path(
        "talents/<int:talent_id>/bookmark/",
        CoachBookmarkTalentAPIView.as_view(),
        name="bookmark_talent"
    ),

    path(
        "bookmarks/<int:bookmark_id>/update/",
        CoachBookmarkUpdateAPIView.as_view(),
        name="bookmark_update"
    ),

    path(
        "bookmarks/<int:bookmark_id>/delete/",
        CoachBookmarkDeleteAPIView.as_view(),
        name="bookmark_delete"
    ),

]

from django.urls import path

from . import views


urlpatterns = [

    path(
        "profile/",
        views.coach_profile,
        name="coach_profile"
    ),

    path(
        "profile/edit/",
        views.edit_coach_profile,
        name="edit_coach_profile"
    ),
    # ----------------------------------------------------- #
    # TALENT DIRECTORY 
    # # ----------------------------------------------------- 
    path(
        "talents/", 
         views.coach_talent_directory,
         name="coach_talent_directory" ), 
    
    path( 
         "talents/<int:talent_id>/", 
         views.coach_view_talent,
         name="coach_view_talent" ),
    
    
        path(
            "talents/<int:talent_id>/save/",
            views.save_talent,
            name="save_talent"
        ),

        path(
            "talents/<int:talent_id>/unsave/",
            views.unsave_talent,
            name="unsave_talent"
        ),

        path(
            "saved-talents/",
            views.saved_talents,
            name="saved_talents"
        ),
        
      
        path(
            "talents/<int:talent_id>/message/",
            views.message_talent,
            name="message_talent"
        ),


        path(
            "analytics/",
            views.coach_analytics,
            name="coach_analytics"
        ),

        path(
            "talents/<int:talent_id>/follow/",
            views.follow_talent,
            name="follow_talent"
        ),

        path(
            "talents/<int:talent_id>/unfollow/",
            views.unfollow_talent,
            name="unfollow_talent"
        ),

        path(
            "talents/<int:talent_id>/note/",
            views.update_talent_note,
            name="update_talent_note"
        ),

        path(
            "talent-directory/",
            views.coach_talent_directory,
            name="coach_talent_directory"
            ),


]

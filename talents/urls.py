from django.urls import path
from . import views


urlpatterns = [

    path(
        "dashboard/",
        views.talent_dashboard,
        name="talent_dashboard"
    ),
    path(
    "verification/request/",
    views.request_verification,
    name="request_verification"
    ),
        
    path(
        "profile/<int:talent_id>/",
        views.talent_profile,
        name="talent_profile"
    ),
    
    path(
        "search/",
        views.talent_search,
        name="talent_search"
    ),    

    path(
        "edit-profile/",
        views.edit_profile,
        name="edit_profile"
    ),
    path(
    "select-category/",
    views.select_talent_category,
    name="select_talent_category"
    ),
    path(
        "search/",
        views.talent_search,
        name="talent_search"
    ),
    path(
        "analytics/",
        views.talent_analytics,
        name="talent_analytics"
    ),

    path(
        "experience/add/",
        views.add_experience,
        name="add_experience"
    ),


    path(
        "experience/delete/<int:experience_id>/",
        views.delete_experience,
        name="delete_experience"
    ),

    path(
        "experience/edit/<int:experience_id>/",
        views.edit_experience,
        name="edit_experience"
    ),
    path(
        "certification/add/",
        views.add_certification,
        name="add_certification"
    ),


    path(
        "certification/edit/<int:certification_id>/",
        views.edit_certification,
        name="edit_certification"
    ),


    path(
        "certification/delete/<int:certification_id>/",
        views.delete_certification,
        name="delete_certification"
    ),
    path(
        "achievement/add/",
        views.add_achievement,
        name="add_achievement"
    ),


    path(
        "achievement/edit/<int:achievement_id>/",
        views.edit_achievement,
        name="edit_achievement"
    ),


    path(
        "achievement/delete/<int:achievement_id>/",
        views.delete_achievement,
        name="delete_achievement"
    ),
    path(
        "invitations/",
        views.talent_invitations,
        name="talent_invitations"
    ),
    
    path(
    "invitations/<int:invitation_id>/accept/",
    views.accept_invitation,
    name="accept_invitation"
     ),


    path(
        "invitations/<int:invitation_id>/decline/",
        views.decline_invitation,
        name="decline_invitation"
    ),
    
    path(
    "profile-strength/",
    views.profile_strength,
    name="profile_strength"
    ),
        
    path(
        "settings/",
        views.talent_settings,
        name="talent_settings"
    ),
    path(
    "role-models/",
    views.role_models,
    name="role_models"
    )
      ,


    path(
        "follow/<int:talent_id>/",
        views.follow_talent,
        name="follow_talent"
    ),


    path(
        "unfollow/<int:talent_id>/",
        views.unfollow_talent,
        name="unfollow_talent"
    ),
    
    path(
    "sports-profile-setup/",
    views.sports_profile_setup,
    name="sports_profile_setup"
),

path(
    "technology-profile-setup/",
    views.technology_profile_setup,
    name="technology_profile_setup"
),

path(
    "arts-profile-setup/",
    views.arts_profile_setup,
    name="arts_profile_setup"
),

path(
    "other-profile-setup/",
    views.other_profile_setup,
    name="other_profile_setup"
),
]
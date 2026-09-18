from django.urls import path

from rest_framework_simplejwt.views import (
    TokenRefreshView,
)

from .views import (
    CourseRecommendationAPIView,
    EventRecommendationAPIView,
    LoginAPIView,
    MeAPIView,
    RoleModelRecommendationAPIView,
    TalentListAPIView,
    TalentDetailAPIView,
    MyTalentProfileAPIView,
    OrganizationListAPIView,
    OrganizationDetailAPIView,
    MyOrganizationAPIView,
    OpportunityListAPIView,
    OpportunityDetailAPIView,
    OpportunityCreateAPIView,
    ApplicationListAPIView,
    ApplicationDetailAPIView,
    ApplicationCreateAPIView,
    ShortlistListAPIView,
    ShortlistDetailAPIView,
    ShortlistCreateAPIView,
    MyShortlistsAPIView,
    RecruitmentStageListAPIView,
    RecruitmentStageDetailAPIView,
    RecruitmentStageCreateAPIView,
    RecruitmentStageUpdateAPIView,
    RecommendationGenerateAPIView,
    RecommendationListAPIView,
    TalentAnalyticsAPIView,
    OrganizationAnalyticsAPIView,
    RecommendationHistoryAPIView,
    TalentProfileViewsAPIView,
    InvitationCreateAPIView,
    SentInvitationsAPIView,
    ReceivedInvitationsAPIView,
    InvitationDetailAPIView,
    InvitationAcceptAPIView,
    InvitationDeclineAPIView,
    ConnectionCreateAPIView,
    MyConnectionsAPIView,
    IncomingConnectionsAPIView,
    OutgoingConnectionsAPIView,
    ConnectionDetailAPIView,
    ConnectionAcceptAPIView,
    ConnectionRejectAPIView,
    ConnectionCancelAPIView,
    FollowUserAPIView,
    UnfollowUserAPIView,
    MyFollowingAPIView,
    MyFollowersAPIView,
    FollowOrganizationAPIView,
    UnfollowOrganizationAPIView,
    MyFollowedOrganizationsAPIView,
    NotificationListAPIView,
    UnreadNotificationsAPIView,
    NotificationDetailAPIView,
    NotificationReadAPIView,
    NotificationReadAllAPIView,
    NotificationCountAPIView,
    ShortlistCreateAPIView,
    MyShortlistsAPIView,
    ShortlistDetailAPIView,
    ShortlistUpdateAPIView,
    ShortlistDeleteAPIView,
    RecruitmentStageCreateAPIView,
    MyRecruitmentPipelineAPIView,
    RecruitmentStageDetailAPIView,
    RecruitmentStageUpdateAPIView,
    RecruitmentStageDeleteAPIView,
    InvitationCreateAPIView,
    ReceivedInvitationsAPIView,
    SentInvitationsAPIView,
    InvitationRespondAPIView,
    InvitationDetailAPIView,
    ConnectionSendAPIView,
    MyConnectionsAPIView,
    ReceivedConnectionsAPIView,
    SentConnectionsAPIView,
    ConnectionRespondAPIView,
    ConnectionDetailAPIView,
    FollowUserAPIView,
    UnfollowUserAPIView,
    MyFollowingAPIView,
    MyFollowersAPIView,
    FollowOrganizationAPIView,
    UnfollowOrganizationAPIView,
    MyFollowedOrganizationsAPIView,
    RoleModelAssignmentListAPIView,
    RoleModelManualAssignmentAPIView,
        
)


app_name = "api"


urlpatterns = [

    # =====================================================
    # AUTHENTICATION
    # =====================================================

    path(
        "auth/login/",
        LoginAPIView.as_view(),
        name="api_login"
    ),

    path(
        "auth/refresh/",
        TokenRefreshView.as_view(),
        name="api_token_refresh"
    ),

    path(
        "auth/me/",
        MeAPIView.as_view(),
        name="api_me"
    ),


    # =====================================================
    # TALENTS
    # =====================================================

    path(
        "talents/",
        TalentListAPIView.as_view(),
        name="talent_list"
    ),

    path(
        "talents/me/",
        MyTalentProfileAPIView.as_view(),
        name="my_talent_profile"
    ),

    path(
        "talents/<int:talent_id>/",
        TalentDetailAPIView.as_view(),
        name="talent_detail"
    ),
    # =====================================================
    # ORGANIZATIONS
    # =====================================================

    path(
        "organizations/",
        OrganizationListAPIView.as_view(),
        name="organization_list"
    ),

    path(
        "organizations/me/",
        MyOrganizationAPIView.as_view(),
        name="my_organization"
    ),

    path(
        "organizations/<int:organization_id>/",
        OrganizationDetailAPIView.as_view(),
        name="organization_detail"
    ),
    
    # =====================================================
    # OPPORTUNITIES
    # =====================================================

    path(
        "opportunities/",
        OpportunityListAPIView.as_view(),
        name="opportunity_list"
    ),

    path(
        "opportunities/<int:opportunity_id>/",
        OpportunityDetailAPIView.as_view(),
        name="opportunity_detail"
    ),
    path(
        "opportunities/create/",
        OpportunityCreateAPIView.as_view(),
        name="opportunity_create"
    ),
    
    # =====================================================
    # APPLICATIONS
    # =====================================================

    path(
        "applications/",
        ApplicationListAPIView.as_view(),
        name="application_list"
    ),

    path(
        "applications/create/",
        ApplicationCreateAPIView.as_view(),
        name="application_create"
    ),

    path(
        "applications/<int:application_id>/",
        ApplicationDetailAPIView.as_view(),
        name="application_detail"
    ),
    # =====================================================
    # SHORTLISTS
    # =====================================================

    path(
        "shortlists/",
        ShortlistListAPIView.as_view(),
        name="shortlist_list"
    ),

    path(
        "shortlists/me/",
        MyShortlistsAPIView.as_view(),
        name="my_shortlists"
    ),

    path(
        "shortlists/create/",
        ShortlistCreateAPIView.as_view(),
        name="shortlist_create"
    ),

    path(
        "shortlists/<int:shortlist_id>/",
        ShortlistDetailAPIView.as_view(),
        name="shortlist_detail"
    ),
    # =====================================================
    # RECRUITMENT PIPELINE
    # =====================================================

    path(
        "recruitment/",
        RecruitmentStageListAPIView.as_view(),
        name="recruitment_list"
    ),

    path(
        "recruitment/create/",
        RecruitmentStageCreateAPIView.as_view(),
        name="recruitment_create"
    ),

    path(
        "recruitment/<int:stage_id>/",
        RecruitmentStageDetailAPIView.as_view(),
        name="recruitment_detail"
    ),

    path(
        "recruitment/<int:stage_id>/update/",
        RecruitmentStageUpdateAPIView.as_view(),
        name="recruitment_update"
    ),
    # =====================================================
    # RECOMMENDATIONS
    # =====================================================

    path(
        "recommendations/<int:opportunity_id>/",
        RecommendationListAPIView.as_view(),
        name="recommendation_list"
    ),

    path(
        "recommendations/<int:opportunity_id>/generate/",
        RecommendationGenerateAPIView.as_view(),
        name="recommendation_generate"
    ),
    # =====================================================
    # ANALYTICS
    # =====================================================

    path(
        "analytics/talent/",
        TalentAnalyticsAPIView.as_view(),
        name="talent_analytics"
    ),

    path(
        "analytics/organization/",
        OrganizationAnalyticsAPIView.as_view(),
        name="organization_analytics"
    ),

    path(
        "analytics/recommendations/",
        RecommendationHistoryAPIView.as_view(),
        name="recommendation_history"
    ),

    path(
        "analytics/profile-views/",
        TalentProfileViewsAPIView.as_view(),
        name="talent_profile_views"
    ),
    
    # =====================================================
    # INVITATIONS
    # =====================================================

    path(
        "invitations/sent/",
        SentInvitationsAPIView.as_view(),
        name="sent_invitations"
    ),

    path(
        "invitations/received/",
        ReceivedInvitationsAPIView.as_view(),
        name="received_invitations"
    ),

    path(
        "invitations/create/",
        InvitationCreateAPIView.as_view(),
        name="invitation_create"
    ),

    path(
        "invitations/<int:invitation_id>/",
        InvitationDetailAPIView.as_view(),
        name="invitation_detail"
    ),

    path(
        "invitations/<int:invitation_id>/accept/",
        InvitationAcceptAPIView.as_view(),
        name="invitation_accept"
    ),

    path(
        "invitations/<int:invitation_id>/decline/",
        InvitationDeclineAPIView.as_view(),
        name="invitation_decline"
    ),
    
    # =====================================================
    # CONNECTIONS
    # =====================================================

    path(
        "connections/",
        MyConnectionsAPIView.as_view(),
        name="my_connections"
    ),

    path(
        "connections/incoming/",
        IncomingConnectionsAPIView.as_view(),
        name="incoming_connections"
    ),

    path(
        "connections/outgoing/",
        OutgoingConnectionsAPIView.as_view(),
        name="outgoing_connections"
    ),

    path(
        "connections/create/",
        ConnectionCreateAPIView.as_view(),
        name="connection_create"
    ),

    path(
        "connections/<int:connection_id>/",
        ConnectionDetailAPIView.as_view(),
        name="connection_detail"
    ),

    path(
        "connections/<int:connection_id>/accept/",
        ConnectionAcceptAPIView.as_view(),
        name="connection_accept"
    ),

    path(
        "connections/<int:connection_id>/reject/",
        ConnectionRejectAPIView.as_view(),
        name="connection_reject"
    ),

    path(
        "connections/<int:connection_id>/cancel/",
        ConnectionCancelAPIView.as_view(),
        name="connection_cancel"
    ),
    # =====================================================
    # FOLLOWS
    # =====================================================

    path(
        "follows/users/",
        MyFollowingAPIView.as_view(),
        name="my_following"
    ),

    path(
        "follows/users/followers/",
        MyFollowersAPIView.as_view(),
        name="my_followers"
    ),

    path(
        "follows/users/<int:user_id>/",
        FollowUserAPIView.as_view(),
        name="follow_user"
    ),

    path(
        "follows/users/<int:user_id>/unfollow/",
        UnfollowUserAPIView.as_view(),
        name="unfollow_user"
    ),

    path(
        "follows/organizations/",
        MyFollowedOrganizationsAPIView.as_view(),
        name="my_followed_organizations"
    ),

    path(
        "follows/organizations/<int:organization_id>/",
        FollowOrganizationAPIView.as_view(),
        name="follow_organization"
    ),

    path(
        "follows/organizations/<int:organization_id>/unfollow/",
        UnfollowOrganizationAPIView.as_view(),
        name="unfollow_organization"
    ),
    
    # =====================================================
    # NOTIFICATIONS
    # =====================================================

    path(
        "notifications/",
        NotificationListAPIView.as_view(),
        name="notification_list"
    ),

    path(
        "notifications/unread/",
        UnreadNotificationsAPIView.as_view(),
        name="notification_unread"
    ),

    path(
        "notifications/count/",
        NotificationCountAPIView.as_view(),
        name="notification_count"
    ),

    path(
        "notifications/read-all/",
        NotificationReadAllAPIView.as_view(),
        name="notification_read_all"
    ),

    path(
        "notifications/<int:notification_id>/",
        NotificationDetailAPIView.as_view(),
        name="notification_detail"
    ),

    path(
        "notifications/<int:notification_id>/read/",
        NotificationReadAPIView.as_view(),
        name="notification_read"
    ),
    
    # =====================================================
    # SHORTLISTS
    # =====================================================

    path(
        "shortlists/",
        MyShortlistsAPIView.as_view(),
        name="my_shortlists"
    ),

    path(
        "shortlists/create/",
        ShortlistCreateAPIView.as_view(),
        name="shortlist_create"
    ),

    path(
        "shortlists/<int:shortlist_id>/",
        ShortlistDetailAPIView.as_view(),
        name="shortlist_detail"
    ),

    path(
        "shortlists/<int:shortlist_id>/update/",
        ShortlistUpdateAPIView.as_view(),
        name="shortlist_update"
    ),

    path(
        "shortlists/<int:shortlist_id>/delete/",
        ShortlistDeleteAPIView.as_view(),
        name="shortlist_delete"
    ),
    # =====================================================
    # RECRUITMENT PIPELINE
    # =====================================================

    path(
        "recruitment/",
        MyRecruitmentPipelineAPIView.as_view(),
        name="recruitment_pipeline"
    ),

    path(
        "recruitment/create/",
        RecruitmentStageCreateAPIView.as_view(),
        name="recruitment_create"
    ),

    path(
        "recruitment/<int:recruitment_id>/",
        RecruitmentStageDetailAPIView.as_view(),
        name="recruitment_detail"
    ),

    path(
        "recruitment/<int:recruitment_id>/update/",
        RecruitmentStageUpdateAPIView.as_view(),
        name="recruitment_update"
    ),

    path(
        "recruitment/<int:recruitment_id>/delete/",
        RecruitmentStageDeleteAPIView.as_view(),
        name="recruitment_delete"
    ),
    
    # =====================================================
    # INVITATIONS
    # =====================================================

    path(
        "invitations/received/",
        ReceivedInvitationsAPIView.as_view(),
        name="received_invitations"
    ),

    path(
        "invitations/sent/",
        SentInvitationsAPIView.as_view(),
        name="sent_invitations"
    ),

    path(
        "invitations/create/",
        InvitationCreateAPIView.as_view(),
        name="invitation_create"
    ),

    path(
        "invitations/<int:invitation_id>/",
        InvitationDetailAPIView.as_view(),
        name="invitation_detail"
    ),

    path(
        "invitations/<int:invitation_id>/respond/",
        InvitationRespondAPIView.as_view(),
        name="invitation_respond"
    ),
    # =====================================================
    # CONNECTIONS
    # =====================================================

    path(
        "connections/",
        MyConnectionsAPIView.as_view(),
        name="my_connections"
    ),

    path(
        "connections/received/",
        ReceivedConnectionsAPIView.as_view(),
        name="received_connections"
    ),

    path(
        "connections/sent/",
        SentConnectionsAPIView.as_view(),
        name="sent_connections"
    ),

    path(
        "connections/send/",
        ConnectionSendAPIView.as_view(),
        name="connection_send"
    ),

    path(
        "connections/<int:connection_id>/",
        ConnectionDetailAPIView.as_view(),
        name="connection_detail"
    ),

    path(
        "connections/<int:connection_id>/respond/",
        ConnectionRespondAPIView.as_view(),
        name="connection_respond"
    ),
    
    # =====================================================
    # FOLLOWS
    # =====================================================

    path(
        "follows/following/",
        MyFollowingAPIView.as_view(),
        name="my_following"
    ),

    path(
        "follows/followers/",
        MyFollowersAPIView.as_view(),
        name="my_followers"
    ),

    path(
        "follows/create/",
        FollowUserAPIView.as_view(),
        name="follow_user"
    ),

    path(
        "follows/<int:user_id>/remove/",
        UnfollowUserAPIView.as_view(),
        name="unfollow_user"
    ),


    # =====================================================
    # ORGANIZATION FOLLOWS
    # =====================================================

    path(
        "organizations/following/",
        MyFollowedOrganizationsAPIView.as_view(),
        name="my_followed_organizations"
    ),

    path(
        "organizations/<int:organization_id>/follow/",
        FollowOrganizationAPIView.as_view(),
        name="follow_organization"
    ),

    path(
        "organizations/<int:organization_id>/unfollow/",
        UnfollowOrganizationAPIView.as_view(),
        name="unfollow_organization"
    ),
    # =====================================================
    # ROLE MODEL MANAGEMENT
    # =====================================================

    path(
        "role-models/",
        RoleModelAssignmentListAPIView.as_view(),
        name="role_model_list"
    ),

    path(
        "role-models/manual/",
        RoleModelManualAssignmentAPIView.as_view(),
        name="role_model_manual"
    ),
    
    path(
    "recommendations/role-models/",
    RoleModelRecommendationAPIView.as_view(),
    name="recommendation_role_models"
    ),

    path(
        "recommendations/courses/",
        CourseRecommendationAPIView.as_view(),
        name="recommendation_courses"
    ),

    path(
        "recommendations/events/",
        EventRecommendationAPIView.as_view(),
        name="recommendation_events"
    ),

]
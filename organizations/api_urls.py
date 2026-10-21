from django.urls import path

from . import api_views
from . import roster_views
from . import agreement_views


app_name = "organization_team"

urlpatterns = [
    path("agreements/", agreement_views.Agreements.as_view(), name="agreements"),
    path("agreements/roster-choices/", agreement_views.RosterChoices.as_view(), name="agreement_roster_choices"),
    path("agreements/destinations/", agreement_views.Destinations.as_view(), name="agreement_destinations"),
    path("agreements/<int:pk>/", agreement_views.AgreementDetail.as_view(), name="agreement"),
    path("agreements/<int:pk>/history/", agreement_views.AgreementHistory.as_view(), name="agreement_history"),
    path("roster-workspaces/", roster_views.Workspaces.as_view(), name="roster_workspaces"),
    path("talent-tags/mine/", roster_views.Mine.as_view(), name="talent_tags_mine"),
    path("talent-tags/<int:pk>/", roster_views.Entry.as_view(), name="talent_tag"),
    path("talent-tags/profile/<int:talent_id>/", roster_views.Badges.as_view(), name="talent_badges"),
    path("<int:organization_id>/roster/", roster_views.Roster.as_view(), name="talent_roster"),
    path("<int:organization_id>/roster/public/", roster_views.Badges.as_view(), name="public_roster"),
    path("<int:organization_id>/team/invitations/", api_views.TeamInvitationListCreateAPIView.as_view(), name="invitation_list_create"),
    path("<int:organization_id>/team/invitations/<int:invitation_id>/revoke/", api_views.TeamInvitationRevokeAPIView.as_view(), name="invitation_revoke"),
    path("<int:organization_id>/team/members/", api_views.TeamMemberListAPIView.as_view(), name="member_list"),
    path("<int:organization_id>/team/members/<int:membership_id>/role/", api_views.TeamMemberRoleAPIView.as_view(), name="member_role"),
    path("<int:organization_id>/team/members/<int:membership_id>/suspend/", api_views.TeamMemberSuspendAPIView.as_view(), name="member_suspend"),
    path("<int:organization_id>/team/members/<int:membership_id>/restore/", api_views.TeamMemberRestoreAPIView.as_view(), name="member_restore"),
    path("<int:organization_id>/team/members/<int:membership_id>/remove/", api_views.TeamMemberRemoveAPIView.as_view(), name="member_remove"),
    path("<int:organization_id>/team/ownership-transfer/", api_views.OwnershipTransferAPIView.as_view(), name="ownership_transfer"),
    path("<int:organization_id>/team/invitations/<int:invitation_id>/accept/", api_views.TeamInvitationAcceptAPIView.as_view(), name="invitation_accept"),
    path("<int:organization_id>/team/invitations/<int:invitation_id>/decline/", api_views.TeamInvitationDeclineAPIView.as_view(), name="invitation_decline"),
]

from django.urls import path

from . import api_views


app_name = "organization_team"

urlpatterns = [
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

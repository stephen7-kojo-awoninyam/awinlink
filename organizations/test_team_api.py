from datetime import timedelta
from unittest.mock import patch

from django.test import override_settings
from django.urls import resolve, reverse
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import User
from . import services
from .models import Organization, OrganizationMembership, OrganizationTeamInvitation


@override_settings(ALLOWED_HOSTS=["testserver"])
class OrganizationTeamAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create(username="team_api_owner", role="ORGANIZATION")
        cls.member_user = User.objects.create(username="team_api_member", role="ATHLETE")
        cls.recipient = User.objects.create(username="team_api_recipient", role="SCOUT")
        cls.outsider = User.objects.create(username="team_api_outsider", role="ADMIN", is_staff=True, is_superuser=True)
        cls.organization = Organization.objects.create(user=cls.owner, name="API Team", country="GH")
        cls.other_org = Organization.objects.create(user=cls.outsider, name="Other API Team", country="GH")
        cls.owner_membership = OrganizationMembership.objects.create(organization=cls.organization, user=cls.owner, role="OWNER")
        cls.member = OrganizationMembership.objects.create(organization=cls.organization, user=cls.member_user, role="RECRUITER")
        cls.other_member = OrganizationMembership.objects.create(organization=cls.other_org, user=cls.member_user, role="MANAGER")
        OrganizationMembership.objects.create(organization=cls.other_org, user=cls.outsider, role="OWNER")

    def url(self, action, **kwargs):
        params = {"organization_id": self.organization.pk}
        params.update(kwargs)
        return reverse(f"api:organization_team:{action}", kwargs=params)

    def invitation(self):
        return services.create_team_invitation(
            organization=self.organization, inviter=self.owner,
            recipient=self.recipient, role="MANAGER",
        )

    def management_requests(self, membership_id=None):
        target = self.member.pk if membership_id is None else membership_id
        return [
            ("get", self.url("member_list"), {}),
            ("patch", self.url("member_role", membership_id=target), {"role": "VIEWER"}),
            ("post", self.url("member_suspend", membership_id=target), {}),
            ("post", self.url("member_restore", membership_id=target), {}),
            ("post", self.url("member_remove", membership_id=target), {}),
            ("post", self.url("ownership_transfer"), {"membership_id": target}),
        ]

    def request(self, method, url, data):
        return getattr(self.client, method)(url, data, format="json")

    def test_every_endpoint_requires_authentication(self):
        invitation, token = self.invitation()
        requests = self.management_requests() + [
            ("post", self.url(action, invitation_id=invitation.pk), {"token": token})
            for action in ("invitation_accept", "invitation_decline")
        ]
        for method, url, data in requests:
            with self.subTest(url=url):
                self.assertEqual(self.request(method, url, data).status_code, 401)

    def test_jwt_authentication_works_and_disabled_accounts_are_rejected(self):
        token = str(AccessToken.for_user(self.owner))
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(self.client.get(self.url("member_list")).status_code, 200)
        User.objects.filter(pk=self.owner.pk).update(is_active=False)
        self.assertEqual(self.client.get(self.url("member_list")).status_code, 401)

    def test_owner_lists_only_scoped_members_without_private_account_fields(self):
        self.client.force_authenticate(self.owner)
        for member_status in ("ACTIVE", "SUSPENDED", "REMOVED"):
            OrganizationMembership.objects.filter(pk=self.member.pk).update(status=member_status)
            response = self.client.get(self.url("member_list"))
            self.assertEqual(response.status_code, 200)
            self.assertEqual({row["id"] for row in response.data}, {self.owner_membership.pk, self.member.pk})
            self.assertEqual(response.data[1]["status"], member_status)
            for row in response.data:
                self.assertEqual(row["organization"], self.organization.pk)
                self.assertNotIn("email", row)
                self.assertNotIn("password", row)
                self.assertNotIn("token_hash", row)

    def test_nonowners_including_managers_and_other_owner_admins_are_denied(self):
        for role in ("MANAGER", "RECRUITER", "VIEWER"):
            OrganizationMembership.objects.filter(pk=self.member.pk).update(role=role)
            self.client.force_authenticate(self.member_user)
            for method, url, data in self.management_requests():
                with self.subTest(role=role, url=url):
                    self.assertEqual(self.request(method, url, data).status_code, 403)
        self.client.force_authenticate(self.outsider)
        for method, url, data in self.management_requests():
            self.assertEqual(self.request(method, url, data).status_code, 403)

    def test_current_database_owner_permissions_override_cached_user_and_legacy_link(self):
        self.client.force_authenticate(self.owner)
        for status in ("SUSPENDED", "REMOVED"):
            OrganizationMembership.objects.filter(pk=self.owner_membership.pk).update(status=status)
            for method, url, data in self.management_requests():
                self.assertEqual(self.request(method, url, data).status_code, 403)
        OrganizationMembership.objects.filter(pk=self.owner_membership.pk).update(role="MANAGER", status="ACTIVE")
        self.assertEqual(self.client.get(self.url("member_list")).status_code, 403)

    def test_inactive_organization_and_disabled_owner_are_denied(self):
        self.client.force_authenticate(self.owner)
        for status in ("INACTIVE", "CLOSED", "MERGED"):
            Organization.objects.filter(pk=self.organization.pk).update(status=status)
            for method, url, data in self.management_requests():
                self.assertEqual(self.request(method, url, data).status_code, 403)
        Organization.objects.filter(pk=self.organization.pk).update(status="ACTIVE")
        User.objects.filter(pk=self.owner.pk).update(is_active=False)
        self.assertEqual(self.client.get(self.url("member_list")).status_code, 403)

    def test_foreign_and_missing_membership_ids_return_404_without_changes(self):
        self.client.force_authenticate(self.owner)
        before = list(OrganizationMembership.objects.order_by("pk").values())
        for target in (self.other_member.pk, 999999):
            for method, url, data in self.management_requests(target)[1:]:
                self.assertEqual(self.request(method, url, data).status_code, 404)
        self.assertEqual(list(OrganizationMembership.objects.order_by("pk").values()), before)

    def test_url_organization_cannot_be_overridden_by_query_or_body(self):
        self.client.force_authenticate(self.owner)
        url = self.url("member_remove", membership_id=self.other_member.pk)
        response = self.client.post(f"{url}?organization_id={self.other_org.pk}",
                                    {"organization": self.other_org.pk, "actor": self.outsider.pk}, format="json")
        self.assertEqual(response.status_code, 404)
        self.other_member.refresh_from_db()
        self.assertEqual(self.other_member.status, "ACTIVE")
        response = self.client.get(self.url("member_list", organization_id=self.other_org.pk))
        self.assertEqual(response.status_code, 403)

    def test_owner_can_change_role_suspend_restore_remove_and_restore(self):
        self.client.force_authenticate(self.owner)
        response = self.client.patch(self.url("member_role", membership_id=self.member.pk), {"role": "VIEWER"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["role"], "VIEWER")
        for action, status in (("member_suspend", "SUSPENDED"), ("member_restore", "ACTIVE"),
                               ("member_remove", "REMOVED"), ("member_restore", "ACTIVE")):
            response = self.client.post(self.url(action, membership_id=self.member.pk), {}, format="json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual((response.data["role"], response.data["status"]), ("VIEWER", status))
        self.assertTrue(OrganizationMembership.objects.filter(pk=self.member.pk).exists())

    def test_management_preserves_global_roles_other_memberships_and_owner_link(self):
        self.client.force_authenticate(self.owner)
        users = list(User.objects.order_by("pk").values())
        other = list(self.other_org.memberships.order_by("pk").values())
        for method, url, data in self.management_requests()[:-1]:
            self.assertEqual(self.request(method, url, data).status_code, 200)
        self.assertEqual(list(User.objects.order_by("pk").values()), users)
        self.assertEqual(list(self.other_org.memberships.order_by("pk").values()), other)
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.user_id, self.owner.pk)

    def test_invalid_and_owner_roles_are_400_and_do_not_mutate_membership(self):
        self.client.force_authenticate(self.owner)
        for data in ({}, {"role": "OWNER"}, {"role": "ADMIN"}, {"role": None}, {"role": []}):
            response = self.client.patch(self.url("member_role", membership_id=self.member.pk), data, format="json")
            self.assertEqual(response.status_code, 400)
        self.member.refresh_from_db()
        self.assertEqual(self.member.role, "RECRUITER")

    def test_sole_owner_demotion_suspension_and_removal_return_400(self):
        self.client.force_authenticate(self.owner)
        for method, url, data in self.management_requests(self.owner_membership.pk)[1:]:
            if "restore" in url:
                continue
            self.assertEqual(self.request(method, url, data).status_code, 400)
        self.owner_membership.refresh_from_db()
        self.assertEqual((self.owner_membership.role, self.owner_membership.status), ("OWNER", "ACTIVE"))

    def test_removed_member_role_change_and_suspension_are_400(self):
        self.client.force_authenticate(self.owner)
        OrganizationMembership.objects.filter(pk=self.member.pk).update(status="REMOVED")
        for method, url, data in self.management_requests()[1:3]:
            self.assertEqual(self.request(method, url, data).status_code, 400)

    def test_transfer_updates_owner_and_immediately_revokes_old_owner_management(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(self.url("ownership_transfer"), {"membership_id": self.member.pk}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"organization": self.organization.pk, "owner": self.member_user.pk})
        self.owner_membership.refresh_from_db()
        self.member.refresh_from_db()
        self.organization.refresh_from_db()
        self.assertEqual(self.owner_membership.role, "MANAGER")
        self.assertEqual(self.member.role, "OWNER")
        self.assertEqual(self.organization.user_id, self.member_user.pk)
        self.assertEqual(self.client.get(self.url("member_list")).status_code, 403)
        self.client.force_authenticate(self.member_user)
        self.assertEqual(self.client.get(self.url("member_list")).status_code, 200)

    def test_invalid_transfer_payloads_and_inactive_successors_return_400(self):
        self.client.force_authenticate(self.owner)
        for data in ({}, {"membership_id": 0}, {"membership_id": "wrong"}, {"membership_id": None}):
            self.assertEqual(self.client.post(self.url("ownership_transfer"), data, format="json").status_code, 400)
        for status in ("SUSPENDED", "REMOVED"):
            OrganizationMembership.objects.filter(pk=self.member.pk).update(status=status)
            self.assertEqual(self.client.post(self.url("ownership_transfer"), {"membership_id": self.member.pk}, format="json").status_code, 400)
        OrganizationMembership.objects.filter(pk=self.member.pk).update(status="ACTIVE")
        User.objects.filter(pk=self.member_user.pk).update(is_active=False)
        self.assertEqual(self.client.post(self.url("ownership_transfer"), {"membership_id": self.member.pk}, format="json").status_code, 400)

    def test_recipient_can_accept_without_existing_organization_access(self):
        invitation, token = self.invitation()
        self.client.force_authenticate(self.recipient)
        response = self.client.post(self.url("invitation_accept", invitation_id=invitation.pk), {"token": token}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "ACCEPTED")
        self.assertNotIn("token", response.data)
        self.assertNotIn("token_hash", response.data)
        self.assertNotIn(token, str(response.data))
        member = self.organization.memberships.get(user=self.recipient)
        self.assertEqual((member.role, member.status), ("MANAGER", "ACTIVE"))

    def test_recipient_can_decline_without_creating_membership(self):
        invitation, token = self.invitation()
        self.client.force_authenticate(self.recipient)
        response = self.client.post(self.url("invitation_decline", invitation_id=invitation.pk), {"token": token}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "DECLINED")
        self.assertNotIn("token_hash", response.data)
        self.assertFalse(self.organization.memberships.filter(user=self.recipient).exists())

    def test_nonrecipient_including_owner_cannot_respond_even_with_valid_token(self):
        invitation, token = self.invitation()
        for user in (self.owner, self.outsider, self.member_user):
            self.client.force_authenticate(user)
            for action in ("invitation_accept", "invitation_decline"):
                response = self.client.post(self.url(action, invitation_id=invitation.pk),
                                            {"token": token, "recipient": self.recipient.pk}, format="json")
                self.assertEqual(response.status_code, 403)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "PENDING")

    def test_invitation_url_scope_and_missing_ids_return_404(self):
        invitation, token = self.invitation()
        self.client.force_authenticate(self.recipient)
        for action in ("invitation_accept", "invitation_decline"):
            for kwargs in ({"organization_id": self.other_org.pk, "invitation_id": invitation.pk}, {"invitation_id": 999999}):
                response = self.client.post(self.url(action, **kwargs), {"token": token}, format="json")
                self.assertEqual(response.status_code, 404)

    def test_invitation_responses_require_body_token_and_reject_invalid_token(self):
        invitation, token = self.invitation()
        self.client.force_authenticate(self.recipient)
        for action in ("invitation_accept", "invitation_decline"):
            url = self.url(action, invitation_id=invitation.pk)
            for data in ({}, {"token": ""}, {"token": None}, {"token": []}, {"token": "x" * 129}):
                self.assertEqual(self.client.post(url, data, format="json").status_code, 400)
            self.assertEqual(self.client.post(f"{url}?token={token}", {}, format="json").status_code, 400)
            self.assertEqual(self.client.post(url, {"token": "wrong"}, format="json").status_code, 403)

    def test_expired_used_revoked_and_declined_invitations_cannot_be_consumed(self):
        invitation, token = self.invitation()
        self.client.force_authenticate(self.recipient)
        for status in ("ACCEPTED", "DECLINED", "REVOKED", "EXPIRED"):
            OrganizationTeamInvitation.objects.filter(pk=invitation.pk).update(status=status)
            for action in ("invitation_accept", "invitation_decline"):
                self.assertEqual(self.client.post(self.url(action, invitation_id=invitation.pk), {"token": token}, format="json").status_code, 400)
        OrganizationTeamInvitation.objects.filter(pk=invitation.pk).update(status="PENDING", expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.post(self.url("invitation_accept", invitation_id=invitation.pk), {"token": token}, format="json").status_code, 400)
        self.assertFalse(self.organization.memberships.filter(user=self.recipient).exists())

    def test_repeated_acceptance_is_400_and_creates_membership_once(self):
        invitation, token = self.invitation()
        self.client.force_authenticate(self.recipient)
        url = self.url("invitation_accept", invitation_id=invitation.pk)
        self.assertEqual(self.client.post(url, {"token": token}, format="json").status_code, 200)
        self.assertEqual(self.client.post(url, {"token": token}, format="json").status_code, 400)
        self.assertEqual(self.organization.memberships.filter(user=self.recipient).count(), 1)

    def test_disabled_recipient_and_demoted_inviter_cannot_accept(self):
        invitation, token = self.invitation()
        self.client.force_authenticate(self.recipient)
        User.objects.filter(pk=self.recipient.pk).update(is_active=False)
        url = self.url("invitation_accept", invitation_id=invitation.pk)
        self.assertEqual(self.client.post(url, {"token": token}, format="json").status_code, 403)
        User.objects.filter(pk=self.recipient.pk).update(is_active=True)
        OrganizationMembership.objects.filter(pk=self.owner_membership.pk).update(role="MANAGER")
        self.assertEqual(self.client.post(url, {"token": token}, format="json").status_code, 403)

    def test_service_rechecks_owner_after_view_object_permission(self):
        self.client.force_authenticate(self.owner)
        original_service = services.list_team_members

        def revoke_before_service(**kwargs):
            OrganizationMembership.objects.filter(pk=self.owner_membership.pk).update(status="REMOVED")
            return original_service(**kwargs)

        with patch.object(services, "list_team_members", side_effect=revoke_before_service):
            self.assertEqual(self.client.get(self.url("member_list")).status_code, 403)

    def test_existing_routes_still_resolve_to_existing_views(self):
        from api import views
        for name, kwargs, view_class in (
            ("organization_list", {}, views.OrganizationListAPIView),
            ("organization_detail", {"organization_id": self.organization.pk}, views.OrganizationDetailAPIView),
            ("my_organization", {}, views.MyOrganizationAPIView),
            ("invitation_accept", {"invitation_id": 1}, views.InvitationAcceptAPIView),
            ("invitation_decline", {"invitation_id": 1}, views.InvitationDeclineAPIView),
        ):
            url = reverse(f"api:{name}", kwargs=kwargs)
            self.assertIs(resolve(url).func.view_class, view_class)

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from .models import Organization, OrganizationMembership, OrganizationTeamInvitation
from .services import create_team_invitation


@override_settings(ALLOWED_HOSTS=["testserver"], STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class OrganizationDashboardIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create(username="dashboard_team_owner", role="ORGANIZATION")
        cls.member = User.objects.create(username="dashboard_team_member", role="ATHLETE")
        cls.recipient = User.objects.create(username="dashboard_team_recipient", role="SCOUT")
        cls.outsider = User.objects.create(username="dashboard_team_outsider", role="ADMIN", is_superuser=True)
        cls.organization = Organization.objects.create(user=cls.owner, name="Dashboard Team", country="GH")
        cls.other_organization = Organization.objects.create(user=cls.outsider, name="Other Dashboard Team", country="GH")
        cls.owner_membership = OrganizationMembership.objects.create(organization=cls.organization, user=cls.owner, role="OWNER")
        cls.membership = OrganizationMembership.objects.create(organization=cls.organization, user=cls.member, role="VIEWER")

    def endpoint(self, action, **kwargs):
        return reverse(f"api:organization_team:{action}", kwargs={"organization_id": self.organization.pk, **kwargs})

    def test_both_dashboard_entry_points_render_the_scoped_workspace(self):
        self.client.force_login(self.owner)
        for route in ("dashboard", "organization_dashboard"):
            response = self.client.get(reverse(route), {"organization_id": self.organization.pk})
            self.assertEqual(response.status_code, 200)
            self.assertTemplateUsed(response, "organizations/dashboard.html")
            self.assertEqual(response.context["organization"], self.organization)
            self.assertTrue(response.context["can_manage_members"])
            self.assertContains(response, "data-team-invite-form")
            self.assertContains(response, self.endpoint("member_list"))

    def test_dashboard_actions_follow_current_membership_capabilities(self):
        self.client.force_login(self.member)
        expected = {"MANAGER": (True, True), "RECRUITER": (False, True), "VIEWER": (False, False)}
        for role, (edit, recruit) in expected.items():
            OrganizationMembership.objects.filter(pk=self.membership.pk).update(role=role)
            response = self.client.get(reverse("organization_dashboard"), {"organization_id": self.organization.pk})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context["can_edit_profile"], edit)
            self.assertEqual(response.context["can_manage_recruitment"], recruit)
            self.assertFalse(response.context["can_manage_members"])
            self.assertNotContains(response, "data-team-invite-form")
            self.assertNotContains(response, "data-members-url=")

    def test_removed_members_inactive_organizations_and_outsiders_are_denied(self):
        self.client.force_login(self.member)
        OrganizationMembership.objects.filter(pk=self.membership.pk).update(status="REMOVED")
        self.assertEqual(self.client.get(reverse("organization_dashboard"), {"organization_id": self.organization.pk}).status_code, 403)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(reverse("organization_dashboard"), {"organization_id": self.organization.pk}).status_code, 403)
        Organization.objects.filter(pk=self.organization.pk).update(status="INACTIVE")
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("organization_dashboard"), {"organization_id": self.organization.pk}).status_code, 403)

    def test_workspace_links_preserve_organization_selection(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("organization_dashboard"))
        for route in ("edit_organization_profile", "create_opportunity", "organization_applications", "recruitment_pipeline", "organization_shortlist"):
            self.assertContains(response, f'{reverse(route)}?organization_id={self.organization.pk}')
        self.assertNotContains(response, self.endpoint("member_list", organization_id=self.other_organization.pk))

    def test_invitation_create_list_and_revoke_use_existing_services(self):
        api = APIClient()
        api.force_authenticate(self.owner)
        response = api.post(self.endpoint("invitation_list_create"), {"recipient_username": f"@{self.recipient.username.upper()}", "role": "MANAGER"}, format="json")
        self.assertEqual(response.status_code, 201)
        invitation = OrganizationTeamInvitation.objects.get(pk=response.data["invitation"]["id"])
        self.assertTrue(invitation.check_token(response.data["token"]))
        self.assertNotEqual(invitation.token_hash, response.data["token"])
        self.assertEqual(response.data["response_url"], reverse("team_invitation_response", args=[invitation.pk]))
        self.assertEqual(response["Cache-Control"], "no-store")
        listing = api.get(self.endpoint("invitation_list_create"))
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data[0]["recipient_username"], self.recipient.username)
        self.assertNotIn("token", listing.data[0])
        self.assertNotIn("token_hash", listing.data[0])
        self.assertEqual(api.post(self.endpoint("invitation_revoke", invitation_id=invitation.pk), {}, format="json").status_code, 200)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "REVOKED")

    def test_pending_duplicates_unknown_accounts_and_owner_roles_are_rejected(self):
        api = APIClient(); api.force_authenticate(self.owner)
        data = {"recipient_username": self.recipient.username, "role": "VIEWER"}
        self.assertEqual(api.post(self.endpoint("invitation_list_create"), data, format="json").status_code, 201)
        self.assertEqual(api.post(self.endpoint("invitation_list_create"), data, format="json").status_code, 400)
        for data in ({"recipient_username": "missing"}, {"recipient_username": self.member.username, "role": "OWNER"}):
            self.assertEqual(api.post(self.endpoint("invitation_list_create"), data, format="json").status_code, 400)
        self.assertEqual(OrganizationTeamInvitation.objects.count(), 1)

    def test_invitation_management_is_owner_only_and_organization_scoped(self):
        invitation, _ = create_team_invitation(organization=self.organization, inviter=self.owner, recipient=self.recipient)
        api = APIClient()
        for user in (self.member, self.outsider):
            api.force_authenticate(user)
            self.assertEqual(api.get(self.endpoint("invitation_list_create")).status_code, 403)
            self.assertEqual(api.post(self.endpoint("invitation_list_create"), {"recipient_username": self.recipient.username}, format="json").status_code, 403)
            self.assertEqual(api.post(self.endpoint("invitation_revoke", invitation_id=invitation.pk), {}, format="json").status_code, 403)
        api.force_authenticate(self.outsider)
        self.assertEqual(api.post(self.endpoint("invitation_revoke", organization_id=self.other_organization.pk, invitation_id=invitation.pk), {}, format="json").status_code, 404)

    def test_recipient_page_is_private_and_does_not_consume_invitation(self):
        invitation, token = create_team_invitation(organization=self.organization, inviter=self.owner, recipient=self.recipient)
        url = reverse("team_invitation_response", args=[invitation.pk])
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.recipient)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.endpoint("invitation_accept", invitation_id=invitation.pk))
        self.assertNotContains(response, token)
        self.assertNotContains(response, invitation.token_hash)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "PENDING")

    def test_session_authenticated_invitation_creation_requires_csrf(self):
        api = APIClient(enforce_csrf_checks=True)
        api.force_login(self.owner)
        api.get(reverse("organization_dashboard"))
        data = {"recipient_username": self.recipient.username}
        self.assertEqual(api.post(self.endpoint("invitation_list_create"), data, format="json").status_code, 403)
        response = api.post(self.endpoint("invitation_list_create"), data, format="json", HTTP_X_CSRFTOKEN=api.cookies["csrftoken"].value)
        self.assertEqual(response.status_code, 201)

    def test_created_invitation_can_be_accepted_by_recipient_with_existing_api(self):
        api = APIClient(); api.force_authenticate(self.owner)
        created = api.post(self.endpoint("invitation_list_create"), {"recipient_username": self.recipient.username, "role": "RECRUITER"}, format="json")
        self.assertEqual(created.status_code, 201)
        invitation_id = created.data["invitation"]["id"]
        api.force_authenticate(self.recipient)
        response = api.post(self.endpoint("invitation_accept", invitation_id=invitation_id), {"token": created.data["token"]}, format="json")
        self.assertEqual(response.status_code, 200)
        membership = OrganizationMembership.objects.get(organization=self.organization, user=self.recipient)
        self.assertEqual((membership.role, membership.status), ("RECRUITER", "ACTIVE"))
        self.recipient.refresh_from_db()
        self.assertEqual(self.recipient.role, "SCOUT")
        self.assertEqual(api.post(self.endpoint("invitation_accept", invitation_id=invitation_id), {"token": created.data["token"]}, format="json").status_code, 400)

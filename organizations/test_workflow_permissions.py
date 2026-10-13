from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from analytics.models import RecommendationHistory
from applications.models import Application
from domains.models import TalentDomain
from invitations.models import Invitation
from opportunities.models import Opportunity
from recruitment.models import RecruitmentStage
from shortlists.models import Shortlist
from talents.models import TalentProfile

from .models import Organization, OrganizationMembership


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class OrganizationWorkflowPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="workflow_owner", role="ORGANIZATION")
        cls.other_owner = User.objects.create_user(username="workflow_other_owner", role="ORGANIZATION")
        cls.legacy_owner = User.objects.create_user(username="workflow_legacy_owner", role="ORGANIZATION")
        cls.organization = Organization.objects.create(user=cls.owner, name="Workflow Org", country="GH")
        cls.other = Organization.objects.create(user=cls.other_owner, name="Other Workflow Org", country="GH")
        cls.legacy = Organization.objects.create(user=cls.legacy_owner, name="Legacy Workflow Org", country="GH")
        cls.manager = User.objects.create_user(username="workflow_manager", role="ATHLETE")
        cls.recruiter = User.objects.create_user(username="workflow_recruiter", role="SCOUT")
        cls.viewer = User.objects.create_user(username="workflow_viewer", role="COACH")
        cls.members = {}
        for user, role in (
            (cls.owner, "OWNER"), (cls.manager, "MANAGER"),
            (cls.recruiter, "RECRUITER"), (cls.viewer, "VIEWER"),
        ):
            cls.members[role] = OrganizationMembership.objects.create(
                organization=cls.organization, user=user, role=role,
            )
        cls.applicant = User.objects.create_user(username="workflow_applicant")
        cls.talent = TalentProfile.objects.create(user=cls.applicant)
        cls.new_applicant = User.objects.create_user(username="workflow_new_applicant")
        cls.new_talent = TalentProfile.objects.create(
            user=cls.new_applicant, profile_visibility="ORGANIZATIONS",
        )
        cls.personal_talent = TalentProfile.objects.create(user=cls.manager, profile_visibility="PRIVATE")
        cls.domain = TalentDomain.objects.create(name="Workflow Domain")
        cls.opportunity = Opportunity.objects.create(
            organization=cls.organization, title="Org A Opportunity", description="First",
            domain=cls.domain,
        )
        cls.other_opportunity = Opportunity.objects.create(
            organization=cls.other, title="Org B Opportunity", description="Other",
            domain=cls.domain,
        )
        cls.application = Application.objects.create(opportunity=cls.opportunity, talent=cls.talent)
        cls.other_application = Application.objects.create(
            opportunity=cls.other_opportunity, talent=cls.talent,
        )
        cls.personal_application = Application.objects.create(
            opportunity=cls.other_opportunity, talent=cls.personal_talent,
        )
        cls.shortlist = Shortlist.objects.create(
            organization=cls.organization, talent=cls.talent, notes="A notes",
        )
        cls.other_shortlist = Shortlist.objects.create(
            organization=cls.other, talent=cls.talent, notes="B notes",
        )
        cls.stage = RecruitmentStage.objects.create(
            organization=cls.organization, talent=cls.talent, opportunity=cls.opportunity,
        )
        cls.other_stage = RecruitmentStage.objects.create(
            organization=cls.other, talent=cls.talent, opportunity=cls.other_opportunity,
        )
        cls.invitation = Invitation.objects.create(
            organization=cls.organization, talent=cls.talent, opportunity=cls.opportunity,
        )
        cls.other_invitation = Invitation.objects.create(
            organization=cls.other, talent=cls.talent, opportunity=cls.other_opportunity,
        )

    def setUp(self):
        self.api = APIClient()

    def actors(self):
        return ((self.owner, "OWNER"), (self.manager, "MANAGER"),
                (self.recruiter, "RECRUITER"), (self.viewer, "VIEWER"))

    def opportunity_data(self, title="New opportunity"):
        return {
            "title": title, "description": "Recruitment opportunity", "domain": self.domain.pk,
            "opportunity_type": "JOB", "experience_level": "BEGINNER", "work_type": "REMOTE",
        }

    def test_profile_read_and_edit_follow_membership_capabilities(self):
        for actor, role in self.actors():
            self.api.force_authenticate(actor)
            self.client.force_login(actor)
            with self.subTest(role=role):
                response = self.api.get("/api/organizations/me/")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["id"], self.organization.pk)
                allowed = role in {"OWNER", "MANAGER"}
                response = self.api.patch(
                    "/api/organizations/me/", {"name": f"Updated by {role}"}, format="json",
                )
                self.assertEqual(response.status_code, 200 if allowed else 403)
                self.assertEqual(
                    self.client.get("/organizations/edit-profile/").status_code,
                    200 if allowed else 403,
                )

    def test_opportunity_create_contract_and_role_permissions(self):
        for actor, role in self.actors():
            self.api.force_authenticate(actor)
            with self.subTest(role=role):
                response = self.api.post(
                    "/api/opportunities/create/",
                    {**self.opportunity_data(role), "organization": self.other.pk},
                    format="json",
                )
                self.assertEqual(response.status_code, 403 if role == "VIEWER" else 201)
                if role != "VIEWER":
                    self.assertEqual(response.data["organization"], self.organization.pk)
                    self.assertEqual(response.data["title"], role)
                    self.assertIn("skills", response.data)
                    self.assertIn("requirements", response.data)

    def test_web_profile_and_opportunity_writes_work_for_a_manager_without_org_account_role(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            "/organizations/edit-profile/", {"name": "Manager profile update", "country": "GH"},
        )
        self.assertEqual(response.status_code, 302)
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.name, "Manager profile update")
        response = self.client.post(
            "/opportunities/create/", {**self.opportunity_data("Manager web opportunity"), "active": "on"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            Opportunity.objects.get(title="Manager web opportunity").organization_id,
            self.organization.pk,
        )

    def test_recruitment_lists_are_scoped_to_the_selected_organization_for_all_roles(self):
        for actor, role in self.actors():
            self.api.force_authenticate(actor)
            with self.subTest(role=role):
                for path, expected in (
                    ("/api/shortlists/", self.shortlist.pk),
                    ("/api/shortlists/me/", self.shortlist.pk),
                    ("/api/recruitment/", self.stage.pk),
                    ("/api/recruitment/pipeline/", self.stage.pk),
                    ("/api/invitations/sent/", self.invitation.pk),
                ):
                    response = self.api.get(path)
                    self.assertEqual(response.status_code, 200, path)
                    self.assertEqual([item["id"] for item in response.data], [expected], path)
                response = self.api.get(
                    "/api/applications/", {"organization_id": self.organization.pk},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual([item["id"] for item in response.data], [self.application.pk])

    def test_recruitment_mutations_allow_owner_manager_recruiter_and_deny_viewer(self):
        for actor, role in self.actors():
            self.api.force_authenticate(actor)
            with self.subTest(role=role):
                expected = 403 if role == "VIEWER" else 200
                for path, body in (
                    (f"/api/shortlists/{self.shortlist.pk}/update/", {"notes": role}),
                    (f"/api/recruitment/{self.stage.pk}/update/", {"stage": "INTERVIEW", "notes": role}),
                    (f"/api/applications/{self.application.pk}/status/", {"status": "REVIEWING"}),
                ):
                    response = self.api.patch(path, body, format="json")
                    self.assertEqual(response.status_code, expected, path)
                for path, body in (
                    ("/api/recruitment/create/", {"talent": self.new_talent.pk, "opportunity": self.opportunity.pk}),
                    ("/api/invitations/create/", {"talent": self.new_talent.pk, "opportunity": self.opportunity.pk, "message": role}),
                    ("/api/shortlists/create/", {"talent": self.new_talent.pk, "notes": role}),
                ):
                    response = self.api.post(path, body, format="json")
                    self.assertEqual(response.status_code, 403 if role == "VIEWER" else 201, path)
                    Invitation.objects.filter(talent=self.new_talent).delete()
                    RecruitmentStage.objects.filter(talent=self.new_talent).delete()
                    Shortlist.objects.filter(talent=self.new_talent).delete()

    def test_viewer_can_read_objects_but_cannot_delete_or_mutate_them(self):
        self.api.force_authenticate(self.viewer)
        self.client.force_login(self.viewer)
        for path in (
            f"/api/applications/{self.application.pk}/",
            f"/api/shortlists/{self.shortlist.pk}/",
            f"/api/recruitment/{self.stage.pk}/",
            f"/api/invitations/{self.invitation.pk}/",
        ):
            self.assertEqual(self.api.get(path).status_code, 200, path)
        for path in (
            f"/api/shortlists/{self.shortlist.pk}/delete/",
            f"/api/recruitment/{self.stage.pk}/delete/",
        ):
            self.assertEqual(self.api.delete(path).status_code, 403)
        for path in (
            f"/applications/accept/{self.application.pk}/",
            f"/recruitment/update/{self.stage.pk}/SELECTED/",
            f"/shortlists/toggle-star/{self.talent.pk}/",
            "/opportunities/create/",
        ):
            self.assertEqual(self.client.post(path, self.opportunity_data()).status_code, 403)
        self.application.refresh_from_db()
        self.stage.refresh_from_db()
        self.shortlist.refresh_from_db()
        self.assertEqual(self.application.status, "PENDING")
        self.assertEqual(self.stage.stage, "SHORTLISTED")
        self.assertFalse(self.shortlist.starred)

    def test_cross_organization_object_reads_writes_and_deletes_are_denied(self):
        self.api.force_authenticate(self.manager)
        self.client.force_login(self.manager)
        for path in (
            f"/api/applications/{self.other_application.pk}/",
            f"/api/shortlists/{self.other_shortlist.pk}/",
            f"/api/recruitment/{self.other_stage.pk}/",
            f"/api/invitations/{self.other_invitation.pk}/",
        ):
            self.assertIn(self.api.get(path).status_code, (403, 404), path)
        for method, path, body in (
            ("patch", f"/api/applications/{self.other_application.pk}/status/", {"status": "ACCEPTED"}),
            ("patch", f"/api/shortlists/{self.other_shortlist.pk}/update/", {"notes": "stolen"}),
            ("patch", f"/api/recruitment/{self.other_stage.pk}/update/", {"stage": "SELECTED"}),
            ("delete", f"/api/shortlists/{self.other_shortlist.pk}/delete/", {}),
            ("delete", f"/api/recruitment/{self.other_stage.pk}/delete/", {}),
        ):
            self.assertIn(getattr(self.api, method)(path, body, format="json").status_code, (403, 404))
        for path in (
            f"/applications/accept/{self.other_application.pk}/",
            f"/recruitment/update/{self.other_stage.pk}/SELECTED/",
            f"/organizations/invite-talent/{self.new_talent.pk}/{self.other_opportunity.pk}/",
        ):
            self.assertIn(self.client.post(path).status_code, (403, 404), path)
        self.other_shortlist.refresh_from_db()
        self.other_stage.refresh_from_db()
        self.other_application.refresh_from_db()
        self.assertEqual(self.other_shortlist.notes, "B notes")
        self.assertEqual(self.other_stage.stage, "SHORTLISTED")
        self.assertEqual(self.other_application.status, "PENDING")

    def test_create_payload_cannot_reference_another_organizations_opportunity(self):
        self.api.force_authenticate(self.manager)
        for path in ("/api/recruitment/create/", "/api/invitations/create/"):
            response = self.api.post(
                path, {"talent": self.new_talent.pk, "opportunity": self.other_opportunity.pk},
                format="json",
            )
            self.assertEqual(response.status_code, 403)
        self.assertFalse(Invitation.objects.filter(talent=self.new_talent).exists())
        self.assertFalse(RecruitmentStage.objects.filter(talent=self.new_talent).exists())

    def test_multiple_memberships_require_selection_for_collections_but_objects_use_actual_scope(self):
        OrganizationMembership.objects.create(organization=self.other, user=self.manager, role="VIEWER")
        self.api.force_authenticate(self.manager)
        self.assertEqual(self.api.get("/api/organizations/me/").status_code, 403)
        for organization in (self.organization, self.other):
            response = self.api.get("/api/organizations/me/", {"organization_id": organization.pk})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["id"], organization.pk)
        self.assertEqual(
            self.api.get(f"/api/shortlists/{self.other_shortlist.pk}/").status_code, 200,
        )
        response = self.api.patch(
            f"/api/shortlists/{self.shortlist.pk}/update/?organization_id={self.other.pk}",
            {"notes": "wrong context"}, format="json",
        )
        self.assertEqual(response.status_code, 403)
        response = self.api.patch(
            f"/api/shortlists/{self.other_shortlist.pk}/update/", {"notes": "viewer cannot write"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        response = self.api.post(
            f"/api/opportunities/create/?organization_id={self.other.pk}",
            self.opportunity_data(), format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_explicit_organization_selection_cannot_grant_access(self):
        self.api.force_authenticate(self.manager)
        for path in ("/api/organizations/me/", "/api/shortlists/", "/api/recruitment/pipeline/"):
            self.assertEqual(self.api.get(path, {"organization_id": self.other.pk}).status_code, 403)
        response = self.api.patch(
            "/api/organizations/me/", {"user": self.manager.pk, "status": "ACTIVE"}, format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.user_id, self.owner.pk)

    def test_legacy_owner_defaults_and_response_contracts_are_preserved(self):
        self.api.force_authenticate(self.legacy_owner)
        response = self.api.get("/api/organizations/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], self.legacy.pk)
        response = self.api.patch("/api/organizations/me/", {"name": "Legacy update"}, format="json")
        self.assertEqual(response.status_code, 200)
        response = self.api.post("/api/opportunities/create/", self.opportunity_data(), format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["organization"], self.legacy.pk)
        self.assertFalse(OrganizationMembership.objects.filter(organization=self.legacy).exists())

    def test_existing_jwt_and_sessions_observe_role_and_membership_revocation(self):
        self.client.force_login(self.manager)
        token = RefreshToken.for_user(self.manager).access_token
        self.api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(self.api.get("/api/organizations/me/").status_code, 200)
        OrganizationMembership.objects.filter(pk=self.members["MANAGER"].pk).update(role="VIEWER")
        self.assertEqual(
            self.api.patch("/api/organizations/me/", {"name": "blocked"}, format="json").status_code,
            403,
        )
        self.assertEqual(self.client.get("/organizations/edit-profile/").status_code, 403)
        for membership_status in ("SUSPENDED", "REMOVED"):
            OrganizationMembership.objects.filter(pk=self.members["MANAGER"].pk).update(status=membership_status)
            self.assertEqual(self.api.get("/api/organizations/me/").status_code, 403)
            self.assertEqual(self.client.get("/recruitment/pipeline/").status_code, 403)
        self.assertEqual(self.api.get("/api/auth/me/").status_code, 200)

    def test_explicit_owner_revocation_cannot_fall_back_to_legacy_user_link(self):
        self.api.force_authenticate(self.owner)
        self.client.force_login(self.owner)
        for membership_status in ("SUSPENDED", "REMOVED"):
            OrganizationMembership.objects.filter(pk=self.members["OWNER"].pk).update(status=membership_status)
            self.assertEqual(self.api.get("/api/organizations/me/").status_code, 403)
            self.assertEqual(self.client.get("/opportunities/create/").status_code, 403)
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.user_id, self.owner.pk)

    def test_inactive_organization_denies_member_workflows_but_preserves_public_and_personal_access(self):
        self.api.force_authenticate(self.manager)
        self.client.force_login(self.manager)
        for organization_status in ("INACTIVE", "MERGED", "CLOSED"):
            Organization.objects.filter(pk=self.organization.pk).update(status=organization_status)
            self.assertEqual(self.api.get("/api/organizations/me/").status_code, 403)
            self.assertEqual(self.client.get("/recruitment/pipeline/").status_code, 403)
            self.assertEqual(
                self.api.post("/api/opportunities/create/", self.opportunity_data(), format="json").status_code,
                403,
            )
        self.assertEqual(self.api.get("/api/auth/me/").status_code, 200)
        self.assertEqual(self.api.get(f"/api/organizations/{self.organization.pk}/").status_code, 200)
        self.manager.refresh_from_db()
        self.assertTrue(self.manager.is_active)

    def test_personal_application_history_and_recipient_invitations_remain_available(self):
        self.api.force_authenticate(self.manager)
        response = self.api.get("/api/applications/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.data], [self.personal_application.pk])
        self.assertEqual(self.api.get(f"/api/applications/{self.personal_application.pk}/").status_code, 200)
        self.api.force_authenticate(self.applicant)
        self.assertEqual(self.api.get(f"/api/invitations/{self.other_invitation.pk}/").status_code, 200)

    def test_member_talent_visibility_is_revoked_with_membership(self):
        self.api.force_authenticate(self.manager)
        response = self.api.get("/api/talents/")
        self.assertIn(self.new_talent.pk, {item["id"] for item in response.data})
        OrganizationMembership.objects.filter(pk=self.members["MANAGER"].pk).update(status="REMOVED")
        response = self.api.get("/api/talents/")
        self.assertNotIn(self.new_talent.pk, {item["id"] for item in response.data})
        self.assertIn(self.personal_talent.pk, {item["id"] for item in response.data})

    @patch("organizations.views.RecommendationEngine.recommend_talents")
    def test_viewer_dashboard_does_not_write_recommendation_history(self, recommend):
        recommend.return_value = [{"talent": self.new_talent, "score": 80, "reasons": []}]
        self.client.force_login(self.viewer)
        count_before = RecommendationHistory.objects.count()
        response = self.client.get("/organizations/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(RecommendationHistory.objects.count(), count_before)

    def test_existing_two_argument_invitation_route_works_and_checks_capabilities(self):
        path = f"/invitations/invite/{self.opportunity.pk}/{self.new_talent.pk}/"
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.post(path, {"message": "Join our opportunity"}).status_code, 302)
        self.assertTrue(Invitation.objects.filter(
            organization=self.organization, talent=self.new_talent, opportunity=self.opportunity,
        ).exists())
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.post(path, {"message": "blocked"}).status_code, 403)

    def test_organization_analytics_checks_current_membership_and_scope(self):
        self.client.force_login(self.viewer)
        response = self.client.get("/analytics/organization/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["organization"].pk, self.organization.pk)
        self.assertEqual(self.client.get("/analytics/organization/", {"organization_id": self.other.pk}).status_code, 403)
        OrganizationMembership.objects.filter(pk=self.members["VIEWER"].pk).update(status="REMOVED")
        self.assertEqual(self.client.get("/analytics/organization/").status_code, 403)

    @patch("api.views.RecommendationEngine.generate_for_organization")
    def test_recommendation_generation_requires_manage_capability_and_actual_scope(self, generate):
        generate.return_value = []
        for user, role in self.actors():
            self.api.force_authenticate(user)
            self.assertEqual(
                self.api.get(f"/api/recommendations/{self.opportunity.pk}/").status_code, 200,
            )
            response = self.api.post(f"/api/recommendations/{self.opportunity.pk}/generate/")
            self.assertEqual(response.status_code, 403 if role == "VIEWER" else 200)
        self.api.force_authenticate(self.manager)
        generate.reset_mock()
        self.assertEqual(
            self.api.post(f"/api/recommendations/{self.other_opportunity.pk}/generate/").status_code, 403,
        )
        generate.assert_not_called()

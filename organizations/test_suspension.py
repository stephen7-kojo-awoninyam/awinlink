from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from advertising.models import Campaign
from advertising.services import transition_campaign
from applications.models import Application
from competitions.models import Competition, CompetitionParticipant
from competitions.services import transition_competition
from domains.models import TalentDomain
from events.models import Event, EventCategory, EventRegistration
from feed.models import Post
from invitations.models import Invitation
from opportunities.models import Opportunity
from recruitment.models import RecruitmentStage
from scouts.models import ScoutProfile
from shortlists.models import Shortlist
from talents.models import TalentProfile

from .models import Organization
from .permissions import require_active_organization


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class OrganizationSuspensionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="suspension_owner", password="TestPass123!", role="ORGANIZATION",
        )
        cls.organization = Organization.objects.create(
            user=cls.owner, name="Suspension Test Org", country="GH",
        )
        cls.other_owner = User.objects.create_user(
            username="active_owner", role="ORGANIZATION",
        )
        cls.other_org = Organization.objects.create(
            user=cls.other_owner, name="Active Test Org", country="GH",
        )
        cls.talent_user = User.objects.create_user(username="suspension_talent")
        cls.talent = TalentProfile.objects.create(user=cls.talent_user)
        cls.domain = TalentDomain.objects.create(name="Suspension Test Domain")
        cls.opportunity = Opportunity.objects.create(
            organization=cls.organization, domain=cls.domain,
            title="Existing Opportunity", description="Preserve this opportunity.",
        )
        cls.application = Application.objects.create(
            opportunity=cls.opportunity, talent=cls.talent, message="Existing application",
        )
        cls.shortlist = Shortlist.objects.create(
            organization=cls.organization, talent=cls.talent, notes="Existing notes",
        )
        cls.stage = RecruitmentStage.objects.create(
            organization=cls.organization, talent=cls.talent, opportunity=cls.opportunity,
        )
        cls.invitation = Invitation.objects.create(
            organization=cls.organization, talent=cls.talent, opportunity=cls.opportunity,
        )
        start = timezone.now() + timedelta(days=3)
        cls.event = Event.objects.create(
            organizer=cls.organization, category=EventCategory.objects.create(name="Test"),
            title="Existing Event", slug="existing-event", description="Existing event",
            event_type="WORKSHOP", location="Accra", start_date=start,
            end_date=start + timedelta(hours=2), status="PUBLISHED",
            registration_deadline=start - timedelta(days=1),
        )
        cls.registration = EventRegistration.objects.create(
            event=cls.event, talent=cls.talent, status="REGISTERED",
        )
        today = timezone.localdate()
        cls.competition = Competition.objects.create(
            organization=cls.organization, title="Existing Competition",
            description="Existing competition", category="SPORTS", discipline="Football",
            status="PUBLISHED", registration_start=today - timedelta(days=1),
            registration_end=today + timedelta(days=7),
            competition_start=today + timedelta(days=8),
            competition_end=today + timedelta(days=10),
        )
        cls.campaign = Campaign.objects.create(
            organization=cls.organization, name="Existing Campaign",
            start_date=today, end_date=today + timedelta(days=7),
            total_budget=Decimal("100"), status="ACTIVE",
        )
        cls.org_post = Post.objects.create(
            author=cls.owner, organization=cls.organization, caption="Existing org post",
        )
        cls.personal_post = Post.objects.create(
            author=cls.owner, caption="Existing personal post",
        )

    def setUp(self):
        self.api = APIClient()

    def suspend(self, status="INACTIVE"):
        Organization.objects.filter(pk=self.organization.pk).update(status=status)

    def assert_records_preserved(self):
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_active)
        for obj in (self.opportunity, self.application, self.shortlist, self.stage,
                    self.invitation, self.event, self.registration, self.competition,
                    self.campaign, self.org_post, self.personal_post):
            self.assertTrue(type(obj).objects.filter(pk=obj.pk).exists())
        self.application.refresh_from_db()
        self.shortlist.refresh_from_db()
        self.stage.refresh_from_db()
        self.invitation.refresh_from_db()
        self.registration.refresh_from_db()
        self.campaign.refresh_from_db()
        self.assertEqual(self.application.status, "PENDING")
        self.assertEqual(self.shortlist.notes, "Existing notes")
        self.assertEqual(self.stage.stage, "SHORTLISTED")
        self.assertEqual(self.invitation.status, "PENDING")
        self.assertEqual(self.registration.status, "REGISTERED")
        self.assertEqual(self.campaign.status, "ACTIVE")

    def test_guard_checks_database_state_and_all_non_active_values(self):
        for status in ("INACTIVE", "MERGED", "CLOSED", "UNKNOWN"):
            with self.subTest(status=status):
                self.suspend(status)
                # The object loaded before suspension still says ACTIVE.
                with self.assertRaises(PermissionDenied):
                    require_active_organization(self.organization)
        self.suspend("ACTIVE")
        self.assertEqual(require_active_organization(self.organization).pk, self.organization.pk)

    def test_suspended_owner_web_workflows_are_blocked_without_record_changes(self):
        self.suspend()
        self.client.force_login(self.owner)
        requests = [
            ("get", "/dashboard/", {}),
            ("get", "/organizations/dashboard/", {}),
            ("get", "/organizations/applications/", {}),
            ("post", "/organizations/edit-profile/", {"name": "Changed"}),
            ("get", "/organizations/talent-search/", {}),
            ("get", reverse("invite_talent", args=[self.talent.pk, self.opportunity.pk]), {}),
            ("get", "/opportunities/create/", {}),
            ("post", f"/applications/accept/{self.application.pk}/", {}),
            ("post", f"/applications/reject/{self.application.pk}/", {}),
            ("post", f"/applications/review/{self.application.pk}/", {}),
            ("post", f"/shortlists/add/{self.talent.pk}/", {}),
            ("post", f"/shortlists/remove/{self.talent.pk}/", {}),
            ("post", f"/shortlists/toggle-star/{self.talent.pk}/", {}),
            ("get", "/recruitment/pipeline/", {}),
            ("post", f"/recruitment/update/{self.stage.pk}/SELECTED/", {}),
            ("get", "/events/create/", {}),
            ("get", "/events/organization/", {}),
            ("get", "/competitions/create/", {}),
            ("get", "/competitions/dashboard/", {}),
            ("get", "/advertising/", {}),
        ]
        for method, path, body in requests:
            with self.subTest(path=path):
                self.assertEqual(getattr(self.client, method)(path, body).status_code, 403)
        self.assert_records_preserved()

    def test_suspended_owner_api_operations_are_blocked_without_record_changes(self):
        self.suspend()
        self.api.force_authenticate(self.owner)
        requests = [
            ("patch", "/api/organizations/me/", {"name": "Changed"}),
            ("post", "/api/opportunities/create/", {}),
            ("get", "/api/applications/", {}),
            ("get", f"/api/applications/{self.application.pk}/", {}),
            ("patch", f"/api/applications/{self.application.pk}/status/", {"status": "ACCEPTED"}),
            ("get", "/api/shortlists/", {}),
            ("post", "/api/shortlists/create/", {}),
            ("patch", f"/api/shortlists/{self.shortlist.pk}/update/", {"notes": "Changed"}),
            ("delete", f"/api/shortlists/{self.shortlist.pk}/delete/", {}),
            ("get", "/api/recruitment/pipeline/", {}),
            ("post", "/api/recruitment/create/", {}),
            ("get", f"/api/recruitment/{self.stage.pk}/", {}),
            ("patch", f"/api/recruitment/{self.stage.pk}/update/", {"stage": "SELECTED"}),
            ("delete", f"/api/recruitment/{self.stage.pk}/delete/", {}),
            ("get", "/api/invitations/sent/", {}),
            ("post", "/api/invitations/create/", {}),
            ("get", f"/api/invitations/{self.invitation.pk}/", {}),
            ("get", "/api/events/my/", {}),
            ("post", "/api/events/create/", {}),
            ("put", f"/api/events/{self.event.pk}/update/", {"title": "Changed"}),
            ("delete", f"/api/events/{self.event.pk}/delete/", {}),
            ("patch", f"/api/events/registrations/{self.registration.pk}/status/", {"status": "APPROVED"}),
            ("post", "/api/competitions/create/", {}),
            ("post", f"/api/competitions/{self.competition.pk}/action/", {"action": "cancel"}),
            ("post", f"/api/competitions/{self.competition.pk}/judges/", {}),
            ("post", "/api/feed/posts/create/", {"caption": "New org post"}),
            ("patch", f"/api/feed/posts/{self.org_post.pk}/update/", {"caption": "Changed"}),
            ("delete", f"/api/feed/posts/{self.org_post.pk}/delete/", {}),
        ]
        for method, path, body in requests:
            with self.subTest(path=path):
                response = getattr(self.api, method)(path, body, format="json")
                self.assertEqual(response.status_code, 403)
        self.assert_records_preserved()

    def test_existing_jwt_and_session_lose_org_access_but_keep_personal_access(self):
        token = RefreshToken.for_user(self.owner).access_token
        self.api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.client.force_login(self.owner)
        self.suspend()
        self.assertEqual(self.api.get("/api/events/my/").status_code, 403)
        self.assertEqual(self.api.get("/api/organizations/me/").status_code, 403)
        self.assertEqual(self.client.get("/organizations/applications/").status_code, 403)
        for path in ("/api/auth/me/", "/api/notifications/", f"/api/organizations/{self.organization.pk}/"):
            self.assertEqual(self.api.get(path).status_code, 200)
        response = self.api.post(
            "/api/auth/login/", {"username": self.owner.username, "password": "TestPass123!"},
        )
        self.assertEqual(response.status_code, 200)
        response = self.api.patch(
            f"/api/feed/posts/{self.personal_post.pk}/update/",
            {"caption": "Personal update"}, format="json",
        )
        self.assertEqual(response.status_code, 200)

    def test_other_active_organization_keeps_access(self):
        self.suspend()
        self.api.force_authenticate(self.other_owner)
        response = self.api.patch(
            "/api/organizations/me/", {"name": "Active org update"}, format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.api.get("/api/events/my/").status_code, 200)
        self.other_owner.refresh_from_db()
        self.assertTrue(self.other_owner.is_active)

    def test_reactivation_restores_operations_without_reenabling_user_accounts(self):
        self.api.force_authenticate(self.owner)
        self.suspend()
        self.assertEqual(self.api.get("/api/events/my/").status_code, 403)
        self.suspend("ACTIVE")
        self.assertEqual(self.api.get("/api/events/my/").status_code, 200)
        response = self.api.patch(
            "/api/organizations/me/", {"name": "Restored organization"}, format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assert_records_preserved()

    def test_suspension_blocks_delegated_scout_shortlist_actions(self):
        scout = User.objects.create_user(username="delegated_scout", role="SCOUT")
        ScoutProfile.objects.create(user=scout, organization=self.organization)
        self.client.force_login(scout)
        self.suspend()
        self.assertEqual(
            self.client.post(f"/shortlists/remove/{self.talent.pk}/").status_code, 403,
        )
        self.assert_records_preserved()

    def test_services_and_ad_delivery_recheck_status_without_mutating_records(self):
        self.suspend()
        with self.assertRaises(PermissionDenied):
            transition_campaign(self.campaign.pk, self.owner, "PAUSED")
        with self.assertRaises(PermissionDenied):
            transition_competition(self.competition, "CANCELLED", self.owner)
        self.assertFalse(self.campaign.is_running())
        self.assert_records_preserved()

    def test_applicant_keeps_history_and_can_decline_existing_invitations(self):
        self.suspend()
        self.api.force_authenticate(self.talent_user)
        self.assertEqual(self.api.get(f"/api/applications/{self.application.pk}/").status_code, 200)
        self.assertEqual(self.api.get(f"/api/invitations/{self.invitation.pk}/").status_code, 200)
        response = self.api.patch(
            f"/api/invitations/{self.invitation.pk}/respond/",
            {"status": "DECLINED"}, format="json",
        )
        self.assertEqual(response.status_code, 200)

    def test_new_applications_and_registrations_are_blocked_for_inactive_org(self):
        self.suspend()
        self.api.force_authenticate(self.talent_user)
        requests = [
            ("/api/applications/create/", {"opportunity": self.opportunity.pk}),
            (f"/api/events/{self.event.pk}/register/", {}),
            (f"/api/competitions/{self.competition.pk}/register/", {}),
            (f"/api/invitations/{self.invitation.pk}/accept/", {}),
        ]
        for path, body in requests:
            with self.subTest(path=path):
                self.assertEqual(self.api.post(path, body, format="json").status_code, 403)
        self.assertFalse(CompetitionParticipant.objects.filter(competition=self.competition).exists())
        self.assert_records_preserved()

    def test_discovery_excludes_inactive_organizations_but_existing_details_remain(self):
        self.suspend()
        self.api.force_authenticate(self.talent_user)
        results = self.api.get("/api/organizations/")
        self.assertEqual(results.status_code, 200)
        ids = {item["id"] for item in results.data}
        self.assertNotIn(self.organization.pk, ids)
        self.assertIn(self.other_org.pk, ids)
        self.assertEqual(
            self.api.get(f"/api/organizations/{self.organization.pk}/").status_code, 200,
        )
        for path, pk in (
            ("/api/opportunities/", self.opportunity.pk),
            ("/api/events/", self.event.pk),
            ("/api/competitions/", self.competition.pk),
        ):
            with self.subTest(path=path):
                response = self.api.get(path)
                self.assertEqual(response.status_code, 200)
                records = response.data if isinstance(response.data, list) else response.data["results"]
                self.assertNotIn(pk, {item["id"] for item in records})

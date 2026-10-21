"""Keep saved invitation paths working while URL names use explicit ID order."""
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase, override_settings
from django.urls import resolve, reverse

from domains.models import TalentDomain
from opportunities.models import Opportunity
from organizations.models import Organization
from organizations import views as organization_views
from recruitment.models import RecruitmentStage
from talents.models import TalentProfile
from . import views
from .models import Invitation


@override_settings(ALLOWED_HOSTS=["testserver"])
class InvitationRoutingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(username="routing_owner", role="ORGANIZATION")
        cls.recipient = User.objects.create_user(username="routing_talent")
        cls.outsider = User.objects.create_user(username="routing_outsider")
        cls.organization = Organization.objects.create(user=cls.owner, name="Routing academy", country="GH")
        domain = TalentDomain.objects.create(name="Routing domain")
        # Explicit unequal IDs reproduce the collision on SQLite and PostgreSQL.
        cls.talent = TalentProfile.objects.create(pk=7101, user=cls.recipient)
        cls.opportunity = Opportunity.objects.create(pk=9202, organization=cls.organization, domain=domain, title="Routing trial")

    def paths(self):
        return [f"/organizations/invite-talent/{self.talent.pk}/{self.opportunity.pk}/",
                f"/invitations/invite/{self.opportunity.pk}/{self.talent.pk}/"]

    def test_distinct_names_reverse_and_resolve_with_unequal_ids(self):
        canonical, legacy = self.paths()
        kwargs = {"talent_id": self.talent.pk, "opportunity_id": self.opportunity.pk}
        self.assertEqual(reverse("invite_talent", args=[self.talent.pk, self.opportunity.pk]), canonical)
        self.assertEqual(reverse("invite_talent", kwargs=kwargs), canonical)
        self.assertEqual(reverse("invite_talent_for_opportunity", args=[self.opportunity.pk, self.talent.pk]), legacy)
        self.assertEqual(reverse("invite_talent_for_opportunity", kwargs=kwargs), legacy)
        self.assertEqual(resolve(canonical).func, organization_views.invite_talent)
        self.assertEqual(resolve(legacy).func, views.invite_talent_for_opportunity)
        for path in self.paths():
            self.assertEqual(resolve(path).kwargs, kwargs)

    def test_both_saved_paths_create_the_same_invitation_and_pipeline(self):
        self.client.force_login(self.owner)
        for path in self.paths():
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["talent"].pk, self.talent.pk)
                self.assertEqual(response.context["opportunity"].pk, self.opportunity.pk)
                self.assertEqual(self.client.post(path, {"message": "Join our trial"}).status_code, 302)
        invitation = Invitation.objects.get()
        stage = RecruitmentStage.objects.get()
        self.assertEqual((invitation.talent_id, invitation.opportunity_id, invitation.organization_id),
                         (self.talent.pk, self.opportunity.pk, self.organization.pk))
        self.assertEqual(invitation.message, "Join our trial")
        self.assertEqual((stage.talent_id, stage.opportunity_id, stage.stage), (self.talent.pk, self.opportunity.pk, "INVITED"))

    def test_both_paths_reject_inactive_organization_and_unrelated_account(self):
        self.client.force_login(self.outsider)
        for path in self.paths():
            self.assertEqual(self.client.get(path).status_code, 403)
            self.assertEqual(self.client.post(path, {"message": "Denied"}).status_code, 403)
        self.client.force_login(self.owner)
        Organization.objects.filter(pk=self.organization.pk).update(status="INACTIVE")
        for path in self.paths():
            self.assertEqual(self.client.get(path).status_code, 403)
            self.assertEqual(self.client.post(path, {"message": "Denied"}).status_code, 403)
        self.assertFalse(Invitation.objects.exists())
        self.assertFalse(RecruitmentStage.objects.exists())

    def test_recommendation_link_uses_named_ids(self):
        # Render both recommendation surfaces to catch swapped positional IDs.
        request = RequestFactory().get("/")
        request.user = self.owner
        for template, key in [("organizations/recommendations.html", "recommendations"),
                              ("recommendations/results.html", "results")]:
            with self.subTest(template=template):
                html = render_to_string(template, {
                    "opportunity": self.opportunity,
                    key: [{"talent": self.talent, "score": 90}],
                }, request=request)
                self.assertIn(f'href="{self.paths()[0]}"', html)

from django.template import Context, Template
from django.test import override_settings, RequestFactory
from django.urls import reverse
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase, APIClient

from accounts.models import User, UserBlock
from talents.models import TalentProfile
from .models import Organization, OrganizationMembership, OrganizationTalent, OrganizationTalentEvent


@override_settings(ALLOWED_HOSTS=["testserver"], STORAGES={
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class TalentRosterTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="roster_owner")
        cls.manager = User.objects.create_user(username="roster_manager")
        cls.recruiter = User.objects.create_user(username="roster_recruiter")
        cls.viewer = User.objects.create_user(username="roster_viewer")
        cls.talent_user = User.objects.create_user(username="roster_talent")
        cls.outsider = User.objects.create_user(username="roster_admin", is_staff=True, is_superuser=True)
        cls.talent = TalentProfile.objects.create(user=cls.talent_user, profile_visibility="PUBLIC")
        cls.org = Organization.objects.create(user=cls.owner, name="Roster Academy", country="GH")
        cls.other = Organization.objects.create(user=cls.outsider, name="Other Academy", country="GH")
        for user, role in [(cls.owner, "OWNER"), (cls.manager, "MANAGER"), (cls.recruiter, "RECRUITER"), (cls.viewer, "VIEWER")]:
            OrganizationMembership.objects.create(organization=cls.org, user=user, role=role)

    def url(self, name, **kwargs):
        return reverse("api:organization_team:" + name, kwargs=kwargs)

    def roster_url(self, org=None):
        return self.url("talent_roster", organization_id=(org or self.org).pk)

    def tag_url(self, entry):
        return self.url("talent_tag", pk=entry["id"] if isinstance(entry, dict) else entry.pk)

    def create(self, linked=True, **extra):
        self.client.force_authenticate(self.manager)
        response = self.client.post(self.roster_url(), {"name": "Talent One", "tag": "Player", "roster": "First team",
            **({"username": self.talent_user.username} if linked else {}), **extra}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def act(self, entry, user, action, **extra):
        self.client.force_authenticate(user)
        return self.client.post(self.tag_url(entry), {"action": action, **extra}, format="json")

    def badges(self):
        return self.client.get(self.url("talent_badges", talent_id=self.talent.pk))

    def test_unclaimed_link_confirm_remove_retains_history_and_accounts(self):
        accounts = User.objects.count()
        entry = self.create(linked=False, talent_details="Forward")
        self.assertEqual(entry["status"], "UNCLAIMED")
        self.assertIsNone(entry["talent_id"])
        self.assertEqual(User.objects.count(), accounts)
        self.assertEqual(self.badges().data["count"], 0)
        linked = self.act(entry, self.recruiter, "LINK", username=self.talent_user.username)
        self.assertEqual(linked.status_code, 200, linked.data)
        self.assertEqual(linked.data["status"], "PENDING")
        self.assertEqual(self.badges().data["count"], 0)
        self.assertEqual(self.act(entry, self.owner, "CONFIRM").status_code, 403)
        self.assertEqual(self.act(entry, self.talent_user, "CONFIRM").status_code, 200)
        self.assertEqual(self.badges().data["count"], 1)
        self.assertEqual(self.act(entry, self.talent_user, "REMOVE", reason="Moved clubs").status_code, 200)
        self.assertEqual(self.badges().data["count"], 0)
        history = self.client.get(self.tag_url(entry))
        self.assertEqual([event["action"] for event in history.data["results"]], ["CREATED", "LINK", "CONFIRM", "REMOVE"])
        self.assertEqual(history.data["results"][-1]["reason"], "Moved clubs")
        self.assertEqual(OrganizationTalent.objects.count(), 1)
        self.assertEqual(User.objects.count(), accounts)

    def test_decline_is_terminal_and_reissue_requires_fresh_confirmation(self):
        entry = self.create()
        self.assertEqual(self.act(entry, self.talent_user, "DECLINE").status_code, 200)
        self.assertEqual(self.act(entry, self.talent_user, "CONFIRM").status_code, 400)
        new = self.create()
        self.assertNotEqual(new["id"], entry["id"])
        self.assertEqual(new["status"], "PENDING")
        self.assertEqual(self.badges().data["count"], 0)

    def test_roles_scope_and_no_admin_bypass(self):
        entry = self.create()
        for user in [self.viewer, self.outsider, self.talent_user]:
            self.client.force_authenticate(user)
            self.assertEqual(self.client.post(self.roster_url(), {"name": "X", "tag": "Member"}, format="json").status_code, 403)
            self.assertEqual(self.act(entry, user, "LINK", username=self.talent_user.username).status_code, 403)
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.client.get(self.roster_url()).status_code, 200)
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(self.roster_url()).status_code, 403)
        self.assertEqual(self.client.get(self.tag_url(entry)).status_code, 403)
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.get(self.roster_url(self.other)).status_code, 403)
        self.assertEqual(self.client.post(self.roster_url(self.other), {"name": "X", "tag": "Member"}, format="json").status_code, 403)

    def test_revocation_and_inactive_organization_rechecked(self):
        entry = self.create()
        OrganizationMembership.objects.filter(user=self.manager).update(status="SUSPENDED")
        self.assertEqual(self.act(entry, self.manager, "REMOVE").status_code, 403)
        Organization.objects.filter(pk=self.org.pk).update(status="INACTIVE")
        self.assertEqual(self.act(entry, self.talent_user, "CONFIRM").status_code, 400)
        # Talents can remove their own tag even after organization suspension.
        self.assertEqual(self.act(entry, self.talent_user, "REMOVE").status_code, 200)
        self.assertEqual(OrganizationTalentEvent.objects.filter(affiliation_id=entry["id"]).count(), 2)

    def test_duplicate_live_link_is_rejected_atomically(self):
        entry = self.create()
        self.client.force_authenticate(self.manager)
        response = self.client.post(self.roster_url(), {"name": "Duplicate", "tag": "Player", "roster": "First team", "username": self.talent_user.username}, format="json")
        self.assertEqual(response.status_code, 400)
        unclaimed = self.create(linked=False)
        self.assertEqual(self.act(unclaimed, self.manager, "LINK", username=self.talent_user.username).status_code, 400)
        self.assertEqual(OrganizationTalent.objects.get(pk=unclaimed["id"]).status, "UNCLAIMED")
        self.assertEqual(OrganizationTalentEvent.objects.count(), 2)
        self.assertEqual(self.act(entry, self.manager, "REMOVE").status_code, 200)
        self.assertEqual(self.act(unclaimed, self.manager, "LINK", username=self.talent_user.username).status_code, 200)

    def test_public_privacy_blocks_and_no_history_leak(self):
        entry = self.create(talent_details="Striker")
        self.act(entry, self.talent_user, "CONFIRM")
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.badges().data["count"], 1)
        self.assertNotIn("history", self.badges().data["results"][0])
        self.assertNotIn("actions", self.badges().data["results"][0])
        for visibility in ["PRIVATE", "ORGANIZATIONS"]:
            TalentProfile.objects.filter(pk=self.talent.pk).update(profile_visibility=visibility)
            self.assertEqual(self.badges().data["count"], 0)
        TalentProfile.objects.filter(pk=self.talent.pk).update(profile_visibility="PUBLIC")
        UserBlock.objects.create(user=self.talent_user, blocked_user=self.viewer)
        self.assertEqual(self.badges().data["count"], 0)
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(self.tag_url(entry)).status_code, 403)
        self.assertEqual(self.client.get(self.url("public_roster", organization_id=self.org.pk)).data["count"], 1)
        User.objects.filter(pk=self.talent_user.pk).update(is_active=False)
        self.assertEqual(self.badges().data["count"], 0)

    def test_validation_and_mass_assignment(self):
        self.client.force_authenticate(self.owner)
        for body in [{"name": "", "tag": "Player"}, {"name": "One", "tag": ""}, {"name": "X", "tag": "x" * 81}, {"name": "X", "tag": "Player", "username": "missing"}]:
            self.assertEqual(self.client.post(self.roster_url(), body, format="json").status_code, 400)
        entry = self.create(status="CONFIRMED", organization_id=self.other.pk, talent_id=self.talent.pk)
        self.assertEqual(entry["organization_id"], self.org.pk)
        self.assertEqual(entry["status"], "PENDING")
        for action in ["DELETE", "UPDATE", ""]:
            self.assertEqual(self.act(entry, self.talent_user, action).status_code, 400)
        self.assertEqual(self.client.delete(self.tag_url(entry)).status_code, 405)

    def test_mine_workspaces_and_authentication(self):
        entry = self.create()
        self.client.force_authenticate(self.talent_user)
        mine = self.client.get(self.url("talent_tags_mine"))
        self.assertEqual([row["id"] for row in mine.data["results"]], [entry["id"]])
        self.assertEqual(mine.data["results"][0]["actions"], ["CONFIRM", "DECLINE", "REMOVE"])
        self.assertEqual(self.client.get(self.url("roster_workspaces")).data["count"], 0)
        self.client.force_authenticate(self.viewer)
        workspace = self.client.get(self.url("roster_workspaces")).data["results"][0]
        self.assertFalse(workspace["can_manage"])
        self.client.force_authenticate(None)
        for path in [self.roster_url(), self.tag_url(entry), self.url("talent_tags_mine"), self.url("roster_workspaces"), self.url("talent_badges", talent_id=self.talent.pk)]:
            self.assertEqual(self.client.get(path).status_code, 401)

    def test_web_page_and_badges_escape_content_and_remove_immediately(self):
        entry = self.create(tag="<script>alert(1)</script>")
        self.act(entry, self.talent_user, "CONFIRM")
        self.client.force_login(self.talent_user)
        page = self.client.get(reverse("organization_talent_rosters"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'name="csrfmiddlewaretoken"')
        request = RequestFactory().get("/"); request.user = self.viewer
        template = Template('{% load roster_tags %}{% organization_talent_badges talent_id=talent_id %}')
        rendered = template.render(Context({"request": request, "talent_id": self.talent.pk}))
        self.assertIn("&lt;script&gt;", rendered)
        self.assertNotIn("<script>", rendered)
        self.act(entry, self.talent_user, "REMOVE")
        self.assertNotIn("Talent confirmed", template.render(Context({"request": request, "talent_id": self.talent.pk})))

    def test_session_writes_require_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.post(self.roster_url(), {"name": "One", "tag": "Player"}, format="json").status_code, 403)

    def test_legacy_owner_and_multiple_organizations_remain_independent(self):
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.post(self.roster_url(self.other), {"name": "Legacy", "tag": "Member"}, format="json").status_code, 201)
        OrganizationMembership.objects.create(organization=self.other, user=self.outsider, role="VIEWER", status="REMOVED")
        self.assertEqual(self.client.post(self.roster_url(self.other), {"name": "Denied", "tag": "Member"}, format="json").status_code, 403)

    def test_blocked_accounts_cannot_be_nominated_or_linked_and_history_is_unchanged(self):
        for peer in [self.manager, self.owner]:
            for reverse_block in [False, True]:
                with self.subTest(peer=peer.username, reverse=reverse_block):
                    block = UserBlock.objects.create(user=self.talent_user if reverse_block else peer,
                        blocked_user=peer if reverse_block else self.talent_user)
                    self.client.force_authenticate(self.manager)
                    before = OrganizationTalentEvent.objects.count()
                    response = self.client.post(self.roster_url(), {"name": "Blocked nomination", "tag": "Member", "username": self.talent_user.username}, format="json")
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(OrganizationTalentEvent.objects.count(), before)
                    entry = self.create(linked=False, tag=f"Blocked {peer.pk} {reverse_block}")
                    self.assertEqual(self.act(entry, self.manager, "LINK", username=self.talent_user.username).status_code, 403)
                    self.assertEqual(OrganizationTalent.objects.get(pk=entry["id"]).status, "UNCLAIMED")
                    self.assertEqual(OrganizationTalentEvent.objects.filter(affiliation_id=entry["id"]).count(), 1)
                    block.delete()

    def test_roster_pagination_does_not_repeat_permission_queries_for_every_entry(self):
        self.create(linked=False)
        self.client.force_authenticate(self.manager)
        with CaptureQueriesContext(connection) as one:
            self.assertEqual(self.client.get(self.roster_url()).status_code, 200)
        OrganizationTalent.objects.bulk_create([OrganizationTalent(organization=self.org, name=f"Player {i:03}", tag="Player") for i in range(50)])
        with CaptureQueriesContext(connection) as many:
            response = self.client.get(self.roster_url())
        self.assertEqual(response.data["count"], 51)
        self.assertEqual(len(response.data["results"]), 50)
        self.assertLessEqual(len(many), len(one) + 1)
        next_page = self.client.get(self.roster_url(), {"page": 2})
        self.assertEqual(len(next_page.data["results"]), 1)
        self.assertIsNone(next_page.data["next"])

    def test_mine_survives_organization_membership_revocation(self):
        entry = self.create()
        member = OrganizationMembership.objects.create(organization=self.org, user=self.talent_user, role="VIEWER")
        member.status = "REMOVED"; member.save(update_fields=["status"])
        self.client.force_authenticate(self.talent_user)
        self.assertEqual(self.client.get(self.roster_url()).status_code, 403)
        mine = self.client.get(self.url("talent_tags_mine"))
        self.assertEqual([row["id"] for row in mine.data["results"]], [entry["id"]])
        self.assertEqual(self.act(entry, self.talent_user, "CONFIRM").status_code, 200)

    def test_public_profile_affiliations_after_the_first_page_are_reachable(self):
        OrganizationTalent.objects.bulk_create([OrganizationTalent(organization=self.org, talent=self.talent,
            name=f"Player {i:03}", tag=f"Tag {i:03}", status="CONFIRMED") for i in range(51)])
        template = Template('{% load roster_tags %}{% organization_talent_badges organization_id=organization_id %}')
        request = RequestFactory().get("/?view=about"); request.user = self.viewer
        first = template.render(Context({"request": request, "organization_id": self.org.pk}))
        self.assertEqual(first.count('class="badge bg-success"'), 50)
        self.assertIn('data-roster-next', first)
        self.assertIn('view=about&amp;roster_page=2', first)
        request = RequestFactory().get("/?roster_page=2"); request.user = self.viewer
        second = template.render(Context({"request": request, "organization_id": self.org.pk}))
        self.assertEqual(second.count('class="badge bg-success"'), 1)
        self.assertIn('Tag 050', second)
        self.assertIn('data-roster-previous', second)

"""Coach/scout badges use the existing consent and organization permission flow."""
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.template import Context, Template
from django.test import RequestFactory, TransactionTestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import User, UserBlock
from coaches.models import CoachProfile
from scouts.models import ScoutProfile
from talents.models import TalentProfile
from .models import Organization, OrganizationMembership, OrganizationTalent, OrganizationTalentEvent


@override_settings(ALLOWED_HOSTS=["testserver"], STORAGES={
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class ProfileBadgeTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="badge-owner", role="ORGANIZATION")
        cls.viewer = User.objects.create_user(username="badge-viewer")
        cls.manager = User.objects.create_user(username="badge-manager")
        cls.outsider = User.objects.create_user(username="badge-admin", is_staff=True, is_superuser=True)
        cls.org = Organization.objects.create(user=cls.owner, name="All categories academy", country="GH")
        OrganizationMembership.objects.create(organization=cls.org, user=cls.manager, role="MANAGER")
        OrganizationMembership.objects.create(organization=cls.org, user=cls.viewer, role="VIEWER")
        cls.profiles = []
        for role, model, field in (("ATHLETE", TalentProfile, "talent_category"),
                                   ("COACH", CoachProfile, "coach_category"),
                                   ("SCOUT", ScoutProfile, "scout_category")):
            for category in ("SPORTS", "SCIENCE_TECHNOLOGY", "ARTS", "OTHERS"):
                user = User.objects.create_user(username=f"badge-{role}-{category}", role=role)
                cls.profiles.append(model.objects.create(user=user, **{field: category}))

    def url(self, name, **kwargs):
        return reverse("api:organization_team:" + name, kwargs=kwargs)

    def create(self, profile=None, **kwargs):
        self.client.force_authenticate(self.manager)
        return self.client.post(self.url("talent_roster", organization_id=self.org.pk), {
            "name": "Roster member", "tag": "Member", "roster": "2026 cohort",
            "username": profile.user.username if profile else "", **kwargs,
        }, format="json")

    def act(self, entry, user, action, **kwargs):
        self.client.force_authenticate(user)
        return self.client.post(self.url("talent_tag", pk=entry["id"]), {"action": action, **kwargs}, format="json")

    def badges(self, profile):
        return self.client.get(self.url("profile_badges", user_id=profile.user_id))

    def test_every_role_and_category_requires_personal_consent_and_retains_history(self):
        accounts = User.objects.count()
        for profile in self.profiles:
            with self.subTest(role=profile.user.role, profile=profile.pk):
                created = self.create(profile)
                self.assertEqual(created.status_code, 201, created.data)
                entry = created.data
                self.assertEqual(entry["status"], "PENDING")
                self.assertEqual(entry["user_id"], profile.user_id)
                self.assertEqual(sum(entry[field] is not None for field in ("talent_id", "coach_id", "scout_id")), 1)
                self.assertEqual(self.badges(profile).data["count"], 0)
                self.assertEqual(self.act(entry, self.owner, "CONFIRM").status_code, 403)
                self.client.force_authenticate(profile.user)
                mine = self.client.get(self.url("talent_tags_mine"))
                self.assertEqual([row["id"] for row in mine.data["results"]], [entry["id"]])
                self.assertEqual(mine.data["results"][0]["actions"], ["CONFIRM", "DECLINE", "REMOVE"])
                self.assertEqual(self.act(entry, profile.user, "CONFIRM").status_code, 200)
                self.client.force_authenticate(self.viewer)
                badge = self.badges(profile).data["results"][0]
                self.assertEqual(badge["user_id"], profile.user_id)
                self.assertIn(badge["category_name"], ["Sports", "Science and technology", "Arts", "Others"])
                self.assertNotIn("actions", badge)
                self.assertNotIn("history", badge)
                self.assertEqual(self.act(entry, profile.user, "REMOVE", reason="Left organization").status_code, 200)
                self.assertEqual(self.badges(profile).data["count"], 0)
                history = self.client.get(self.url("talent_tag", pk=entry["id"])).data["results"]
                self.assertEqual([row["action"] for row in history], ["REQUESTED", "CONFIRM", "REMOVE"])
                self.assertEqual(history[-1]["reason"], "Left organization")
        self.assertEqual(User.objects.count(), accounts)

    def test_link_unclaimed_decline_and_reissue_require_fresh_consent(self):
        for profile in self.profiles[4:]:
            entry = self.create().data
            self.assertEqual(entry["status"], "UNCLAIMED")
            linked = self.act(entry, self.manager, "LINK", username=profile.user.username)
            self.assertEqual(linked.status_code, 200, linked.data)
            self.assertEqual(linked.data["user_id"], profile.user_id)
            self.assertEqual(self.act(entry, profile.user, "DECLINE").status_code, 200)
            self.assertEqual(self.act(entry, profile.user, "CONFIRM").status_code, 400)
            reissued = self.create(profile)
            self.assertEqual(reissued.status_code, 201, reissued.data)
            self.assertEqual(reissued.data["status"], "PENDING")
            self.assertEqual(self.badges(profile).data["count"], 0)

    def test_duplicate_proposals_and_links_are_atomic_for_coaches_and_scouts(self):
        for profile in (self.profiles[4], self.profiles[8]):
            entry = self.create(profile).data
            count = OrganizationTalentEvent.objects.count()
            self.assertEqual(self.create(profile).status_code, 400)
            self.assertEqual(OrganizationTalentEvent.objects.count(), count)
            unclaimed = self.create().data
            self.assertEqual(self.act(unclaimed, self.manager, "LINK", username=profile.user.username).status_code, 400)
            self.assertEqual(OrganizationTalent.objects.get(pk=unclaimed["id"]).status, "UNCLAIMED")
            self.assertEqual(self.act(entry, profile.user, "REMOVE").status_code, 200)
            self.assertEqual(self.act(unclaimed, self.manager, "LINK", username=profile.user.username).status_code, 200)

    def test_permissions_revocation_inactive_organization_and_no_admin_bypass(self):
        for profile in (self.profiles[4], self.profiles[8]):
            entry = self.create(profile).data
            for user in (self.viewer, self.outsider):
                self.assertEqual(self.act(entry, user, "CONFIRM").status_code, 403)
                self.assertEqual(self.act(entry, user, "REMOVE").status_code, 403)
            self.client.force_authenticate(self.outsider)
            self.assertEqual(self.client.get(self.url("talent_tag", pk=entry["id"])).status_code, 403)
            OrganizationMembership.objects.filter(user=self.manager).update(status="SUSPENDED")
            self.assertEqual(self.act(entry, self.manager, "REMOVE").status_code, 403)
            Organization.objects.filter(pk=self.org.pk).update(status="INACTIVE")
            self.assertEqual(self.act(entry, profile.user, "CONFIRM").status_code, 400)
            self.assertEqual(self.act(entry, profile.user, "REMOVE").status_code, 200)
            OrganizationMembership.objects.filter(user=self.manager).update(status="ACTIVE")
            Organization.objects.filter(pk=self.org.pk).update(status="ACTIVE")

    def test_blocked_and_inactive_profiles_cannot_be_nominated_or_published(self):
        for profile in (self.profiles[4], self.profiles[8]):
            for peer in (self.manager, self.owner):
                for blocker, blocked in ((profile.user, peer), (peer, profile.user)):
                    block = UserBlock.objects.create(user=blocker, blocked_user=blocked)
                    before = OrganizationTalentEvent.objects.count()
                    self.assertEqual(self.create(profile).status_code, 403)
                    self.assertEqual(OrganizationTalentEvent.objects.count(), before)
                    block.delete()
            entry = self.create(profile).data
            self.act(entry, profile.user, "CONFIRM")
            self.client.force_authenticate(self.viewer)
            self.assertEqual(self.badges(profile).data["count"], 1)
            block = UserBlock.objects.create(user=profile.user, blocked_user=self.viewer)
            self.assertEqual(self.badges(profile).data["count"], 0)
            block.delete()
            User.objects.filter(pk=profile.user_id).update(is_active=False)
            self.assertEqual(self.badges(profile).data["count"], 0)
            self.assertEqual(self.create(profile).status_code, 400)

    def test_profile_identity_cannot_be_mass_assigned_or_changed_by_a_manager(self):
        coach, scout = self.profiles[4], self.profiles[8]
        entry = self.create(coach, scout_id=scout.pk, status="CONFIRMED").data
        self.assertEqual(entry["coach_id"], coach.pk)
        self.assertIsNone(entry["scout_id"])
        self.assertEqual(entry["status"], "PENDING")
        self.assertEqual(self.act(entry, self.manager, "LINK", username=scout.user.username).status_code, 400)
        with self.assertRaises(IntegrityError), transaction.atomic():
            OrganizationTalent.objects.filter(pk=entry["id"]).update(scout=scout)

    def test_public_web_badges_escape_coach_and_scout_names_and_remove_immediately(self):
        template = Template('{% load roster_tags %}{% organization_talent_badges user_id=user_id %}')
        org_template = Template('{% load roster_tags %}{% organization_talent_badges organization_id=organization_id %}')
        request = RequestFactory().get("/"); request.user = self.viewer
        for profile in (self.profiles[4], self.profiles[8]):
            entry = self.create(profile, tag="<script>Coach</script>").data
            self.act(entry, profile.user, "CONFIRM")
            context = Context({"request": request, "user_id": profile.user_id})
            html = template.render(context)
            self.assertIn("&lt;script&gt;", html)
            self.assertNotIn("<script>", html)
            self.assertIn(profile.user.role.title() + " confirmed", html)
            org_html = org_template.render(Context({"request": request, "organization_id": self.org.pk}))
            self.assertIn(profile.user.username, org_html)
            self.act(entry, profile.user, "REMOVE")
            self.assertNotIn("confirmed", template.render(context))
        self.assertNotIn("confirmed", template.render(Context({"request": request})))

    def test_badges_require_authentication_and_talent_agreements_remain_talent_scoped(self):
        profile = self.profiles[4]
        entry = self.create(profile).data
        self.act(entry, profile.user, "CONFIRM")
        self.client.force_authenticate(self.owner)
        choices = self.client.get(self.url("agreement_roster_choices"))
        self.assertNotIn(entry["id"], [row["id"] for row in choices.data["results"]])
        self.client.force_authenticate(None)
        self.assertEqual(self.badges(profile).status_code, 401)

    def test_profile_pages_show_confirmed_badges_and_management_link(self):
        for profile, page_name in ((self.profiles[4], "coach_profile"), (self.profiles[8], "scout_dashboard")):
            entry = self.create(profile).data
            self.act(entry, profile.user, "CONFIRM")
            self.client.force_login(profile.user)
            page = self.client.get(reverse(page_name))
            self.assertEqual(page.status_code, 200)
            self.assertContains(page, self.org.name)
            self.assertContains(page, "Manage organization tags")
            self.assertContains(page, profile.user.role.title() + " confirmed")

    def test_other_profile_owner_cannot_respond_or_read_private_history(self):
        coach, scout = self.profiles[4], self.profiles[8]
        entry = self.create(coach).data
        self.assertEqual(self.act(entry, scout.user, "CONFIRM").status_code, 403)
        self.assertEqual(self.act(entry, scout.user, "DECLINE").status_code, 403)
        self.client.force_authenticate(scout.user)
        self.assertEqual(self.client.get(self.url("talent_tag", pk=entry["id"])).status_code, 403)
        self.assertEqual(self.client.get(self.url("talent_tags_mine")).data["count"], 0)

    def test_constraints_and_rollback_guard_preserve_profile_consent_links(self):
        from importlib import import_module
        from types import SimpleNamespace
        from django.apps import apps
        from django.db.migrations.exceptions import IrreversibleError
        from django.db.models.deletion import ProtectedError
        coach = self.profiles[4]
        migration = import_module("organizations.migrations.0014_coach_scout_roster_badges")
        for values in ({"coach": coach, "status": "UNCLAIMED"}, {"status": "CONFIRMED"}):
            with self.assertRaises(IntegrityError), transaction.atomic():
                OrganizationTalent.objects.create(organization=self.org, name="Invalid", tag="Member", **values)
        entry = self.create(coach).data
        self.act(entry, coach.user, "REMOVE")
        with self.assertRaises(IrreversibleError):
            migration.protect_profile_links(apps, SimpleNamespace(connection=connection))
        with self.assertRaises(ProtectedError):
            coach.delete()
        self.assertEqual(OrganizationTalentEvent.objects.filter(affiliation_id=entry["id"]).count(), 2)


class ProfileBadgeMigrationTests(TransactionTestCase):
    def restore_schema(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_forward_migration_preserves_existing_rosters_consent_and_history(self):
        self.addCleanup(self.restore_schema)
        executor = MigrationExecutor(connection)
        before = [("organizations", "0013_roster_agreements")]
        executor.migrate(before)
        # A leaf in another app can depend on a newer organizations migration.
        # Use the actual applied graph after rollback, rather than reintroducing
        # those newer fields through the hypothetical leaf-node state.
        state = executor.loader.project_state(list(MigrationRecorder(connection).applied_migrations())).apps
        user = state.get_model("accounts", "User").objects.create(username="migration-badge")
        organization = state.get_model("organizations", "Organization").objects.create(user_id=user.pk, name="Preserve", country="GH")
        talent = state.get_model("talents", "TalentProfile").objects.create(user_id=user.pk)
        entry = state.get_model("organizations", "OrganizationTalent").objects.create(
            organization_id=organization.pk, talent_id=talent.pk, name="Existing", tag="Member", status="CONFIRMED")
        event = state.get_model("organizations", "OrganizationTalentEvent").objects.create(affiliation_id=entry.pk, actor_id=user.pk, action="CONFIRM", reason="Keep consent")
        saved = state.get_model("organizations", "OrganizationTalent").objects.values().get(pk=entry.pk)
        saved_event = state.get_model("organizations", "OrganizationTalentEvent").objects.values().get(pk=event.pk)
        self.restore_schema()
        current = OrganizationTalent.objects.values().get(pk=entry.pk)
        self.assertEqual({key: current[key] for key in saved}, saved)
        self.assertIsNone(current["coach_id"])
        self.assertIsNone(current["scout_id"])
        self.assertEqual(OrganizationTalentEvent.objects.values().get(pk=event.pk), saved_event)

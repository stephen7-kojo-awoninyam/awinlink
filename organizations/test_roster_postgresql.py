from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.db import close_old_connections, connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from rest_framework.exceptions import ValidationError

from accounts.models import User
from talents.models import TalentProfile
from .models import Organization, OrganizationMembership, OrganizationTalent, OrganizationTalentEvent
from .roster_services import create_entry, transition


@skipUnless(connection.vendor == "postgresql", "PostgreSQL migration and row locks")
class RosterPostgresTests(TransactionTestCase):
    def setUp(self):
        self.owner = User.objects.create(username="roster_pg_owner")
        self.user = User.objects.create(username="roster_pg_talent")
        self.talent = TalentProfile.objects.create(user=self.user)
        self.organization = Organization.objects.create(user=self.owner, name="PG roster", country="GH")

    def race(self, first, second):
        barrier = Barrier(2)
        def run(operation):
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                operation()
                return "ok"
            except ValidationError:
                return "conflict"
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run, op) for op in [first, second]]
            return [future.result(timeout=30) for future in futures]

    def test_concurrent_duplicate_proposals_have_one_row_and_event(self):
        def create():
            create_entry(self.organization.pk, self.owner, {"name": "One", "tag": "Player", "username": self.user.username})
        self.assertEqual(sorted(self.race(create, create)), ["conflict", "ok"])
        self.assertEqual(OrganizationTalent.objects.count(), 1)
        self.assertEqual(OrganizationTalentEvent.objects.count(), 1)

    def test_concurrent_confirmations_record_one_decision(self):
        entry = create_entry(self.organization.pk, self.owner, {"name": "One", "tag": "Player", "username": self.user.username})
        def confirm():
            transition(entry.pk, self.user, "CONFIRM")
        self.assertEqual(sorted(self.race(confirm, confirm)), ["conflict", "ok"])
        entry.refresh_from_db()
        self.assertEqual(entry.status, "CONFIRMED")
        self.assertEqual(entry.history.count(), 2)

    def test_forward_migration_preserves_existing_organization_and_talent(self):
        executor = MigrationExecutor(connection)
        before = [("organizations", "0011_organization_team_invitation")]
        executor.migrate(before)
        self.addCleanup(self.restore_schema)
        targets = [node for node in executor.loader.graph.leaf_nodes() if node[0] != "organizations"] + before
        apps = executor.loader.project_state(targets).apps
        OrganizationOld = apps.get_model("organizations", "Organization")
        TalentOld = apps.get_model("talents", "TalentProfile")
        MembershipOld = apps.get_model("organizations", "OrganizationMembership")
        membership = MembershipOld.objects.create(organization_id=self.organization.pk, user_id=self.owner.pk, role="OWNER")
        saved_org = OrganizationOld.objects.values().get(pk=self.organization.pk)
        saved_talent = TalentOld.objects.values().get(pk=self.talent.pk)
        saved_member = MembershipOld.objects.values().get(pk=membership.pk)
        executor = MigrationExecutor(connection)
        leaves = executor.loader.graph.leaf_nodes()
        executor.migrate(leaves)
        new = executor.loader.project_state(leaves).apps
        self.assertEqual(new.get_model("organizations", "Organization").objects.values().get(pk=self.organization.pk), saved_org)
        self.assertEqual(new.get_model("talents", "TalentProfile").objects.values().get(pk=self.talent.pk), saved_talent)
        self.assertEqual(new.get_model("organizations", "OrganizationMembership").objects.values().get(pk=membership.pk), saved_member)
        self.assertFalse(new.get_model("organizations", "OrganizationTalent").objects.exists())
        self.assertFalse(new.get_model("organizations", "OrganizationTalentEvent").objects.exists())

    def restore_schema(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

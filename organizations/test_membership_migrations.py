from importlib import import_module
from types import SimpleNamespace

from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.test import TransactionTestCase


BACKFILL = ("organizations", "0010_backfill_existing_owners")
SCHEMA = ("organizations", "0009_organization_membership")
LEGACY = ("organizations", "0008_organization_cover_photo_organization_followers")


class MembershipMigrationTestCase(TransactionTestCase):
    migrate_from = LEGACY

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        self.latest_targets = executor.loader.graph.leaf_nodes()
        self.addCleanup(self.restore_latest)
        self.old_apps = self.migrate(self.migrate_from)

    def restore_latest(self):
        MigrationExecutor(connection).migrate(self.latest_targets)

    def migrate(self, target):
        executor = MigrationExecutor(connection)
        executor.migrate([target])
        # Account migrations remain applied while this app is rolled back.
        return executor.loader.project_state(list(MigrationRecorder(connection).applied_migrations())).apps

    def legacy_owner(self, username, organization_status="ACTIVE", role="ORGANIZATION",
                     is_active=True):
        User = self.old_apps.get_model(*settings.AUTH_USER_MODEL.split("."))
        Organization = self.old_apps.get_model("organizations", "Organization")
        user = User.objects.create(username=username, role=role, is_active=is_active)
        organization = Organization.objects.create(
            user_id=user.pk, name=username, country="GH", status=organization_status,
        )
        return user, organization

    def replay(self, apps):
        migration = import_module("organizations.migrations.0010_backfill_existing_owners")
        migration.backfill_existing_owners(
            apps, SimpleNamespace(connection=connection),
        )


class ExistingOwnerBackfillMigrationTests(MembershipMigrationTestCase):
    def test_backfill_preserves_legacy_owner_links_records_and_account_states(self):
        pairs = []
        for status, role in zip(
            ("ACTIVE", "INACTIVE", "MERGED", "CLOSED"),
            ("ORGANIZATION", "ATHLETE", "SCOUT", "COACH"),
        ):
            pairs.append(self.legacy_owner(f"legacy_{status.lower()}", status, role))
        pairs.append(self.legacy_owner(
            "legacy_disabled_admin", "INACTIVE", "ADMIN", is_active=False,
        ))
        Organization = self.old_apps.get_model("organizations", "Organization")
        User = self.old_apps.get_model(*settings.AUTH_USER_MODEL.split("."))
        unclaimed = Organization.objects.create(
            name="Unclaimed", country="GH", status="ACTIVE",
        )
        pairs[0][1].followers.add(pairs[1][0])
        organization_records = list(Organization.objects.order_by("pk").values())
        user_records = list(User.objects.order_by("pk").values())

        apps = self.migrate(BACKFILL)
        Organization = apps.get_model("organizations", "Organization")
        User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
        Membership = apps.get_model("organizations", "OrganizationMembership")

        expected = [(organization.pk, user.pk, "OWNER", "ACTIVE") for user, organization in pairs]
        actual = list(Membership.objects.order_by("organization_id").values_list(
            "organization_id", "user_id", "role", "status",
        ))
        self.assertEqual(actual, expected)
        self.assertEqual(list(Organization.objects.order_by("pk").values()), organization_records)
        self.assertEqual(list(User.objects.order_by("pk").values()), user_records)
        self.assertFalse(Membership.objects.filter(organization_id=unclaimed.pk).exists())
        self.assertEqual(
            list(Organization.objects.get(pk=pairs[0][1].pk).followers.values_list("pk", flat=True)),
            [pairs[1][0].pk],
        )

    def test_backfill_can_run_again_without_duplicates_or_timestamp_changes(self):
        user, organization = self.legacy_owner("legacy_repeat")
        apps = self.migrate(BACKFILL)
        Membership = apps.get_model("organizations", "OrganizationMembership")
        records = list(Membership.objects.values())
        self.replay(apps)
        self.replay(apps)
        self.assertEqual(list(Membership.objects.values()), records)
        self.assertEqual(
            Membership.objects.get(organization_id=organization.pk).user_id, user.pk,
        )

    def test_schema_migration_enforces_both_unique_constraints_before_backfill(self):
        user, organization = self.legacy_owner("legacy_constraint")
        apps = self.migrate(SCHEMA)
        Membership = apps.get_model("organizations", "OrganizationMembership")
        User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
        other = User.objects.create(username="legacy_constraint_other")
        Membership.objects.create(
            organization_id=organization.pk, user_id=user.pk,
            role="OWNER", status="ACTIVE",
        )
        for user_id, role, status in (
            (user.pk, "VIEWER", "REMOVED"),
            (other.pk, "OWNER", "ACTIVE"),
        ):
            with self.subTest(user_id=user_id), self.assertRaises(IntegrityError), transaction.atomic():
                Membership.objects.create(
                    organization_id=organization.pk, user_id=user_id,
                    role=role, status=status,
                )
        self.assertEqual(Membership.objects.count(), 1)


class MembershipBackfillReplayMigrationTests(MembershipMigrationTestCase):
    migrate_from = SCHEMA

    def test_existing_memberships_are_preserved_without_promotion_or_reactivation(self):
        Membership = self.old_apps.get_model("organizations", "OrganizationMembership")
        for index, (role, status) in enumerate((
            ("OWNER", "ACTIVE"), ("OWNER", "REMOVED"), ("OWNER", "SUSPENDED"),
            ("MANAGER", "ACTIVE"), ("RECRUITER", "SUSPENDED"), ("VIEWER", "REMOVED"),
        )):
            user, organization = self.legacy_owner(f"existing_member_{index}")
            Membership.objects.create(
                organization_id=organization.pk, user_id=user.pk,
                role=role, status=status,
            )
        records = list(Membership.objects.order_by("pk").values())

        apps = self.migrate(BACKFILL)
        Membership = apps.get_model("organizations", "OrganizationMembership")
        self.assertEqual(list(Membership.objects.order_by("pk").values()), records)

    def test_conflicting_active_owner_aborts_and_rolls_back_the_entire_backfill(self):
        first_user, first_org = self.legacy_owner("first_legacy_owner")
        second_user, second_org = self.legacy_owner("conflicted_legacy_owner")
        Membership = self.old_apps.get_model("organizations", "OrganizationMembership")
        User = self.old_apps.get_model(*settings.AUTH_USER_MODEL.split("."))
        different_owner = User.objects.create(username="different_active_owner")
        conflict = Membership.objects.create(
            organization_id=second_org.pk, user_id=different_owner.pk,
            role="OWNER", status="ACTIVE",
        )
        try:
            with self.assertRaisesRegex(RuntimeError, "active owner membership belongs to another user"):
                self.migrate(BACKFILL)
            self.assertFalse(Membership.objects.filter(organization_id=first_org.pk).exists())
            self.assertEqual(Membership.objects.count(), 1)
            self.assertEqual(Membership.objects.get(pk=conflict.pk).user_id, different_owner.pk)
            self.assertNotIn(BACKFILL, MigrationRecorder(connection).applied_migrations())
            Organization = self.old_apps.get_model("organizations", "Organization")
            self.assertEqual(Organization.objects.get(pk=first_org.pk).user_id, first_user.pk)
            self.assertEqual(Organization.objects.get(pk=second_org.pk).user_id, second_user.pk)
        finally:
            # Repair this deliberate test conflict so cleanup can restore migration state.
            Membership.objects.filter(pk=conflict.pk).update(status="REMOVED")

    def test_reversing_data_migration_keeps_memberships_and_later_changes(self):
        user, organization = self.legacy_owner("reverse_legacy_owner")
        apps = self.migrate(BACKFILL)
        Membership = apps.get_model("organizations", "OrganizationMembership")
        User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
        manager = User.objects.create(username="later_manager")
        Membership.objects.create(
            organization_id=organization.pk, user_id=manager.pk,
            role="MANAGER", status="ACTIVE",
        )
        Membership.objects.filter(
            organization_id=organization.pk, user_id=user.pk,
        ).update(status="SUSPENDED")
        records = list(Membership.objects.order_by("pk").values())

        apps = self.migrate(SCHEMA)
        Membership = apps.get_model("organizations", "OrganizationMembership")
        Organization = apps.get_model("organizations", "Organization")
        self.assertEqual(list(Membership.objects.order_by("pk").values()), records)
        self.assertEqual(Organization.objects.get(pk=organization.pk).user_id, user.pk)
        apps = self.migrate(BACKFILL)
        Membership = apps.get_model("organizations", "OrganizationMembership")
        self.assertEqual(list(Membership.objects.order_by("pk").values()), records)

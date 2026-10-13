from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from time import sleep
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, OperationalError, close_old_connections, connection
from django.test import TestCase, TransactionTestCase

from accounts.models import User
from .models import Organization, OrganizationMembership
from .permissions import get_organization_role
from .services import (
    remove_team_member, suspend_team_member, transfer_organization_ownership,
)


class OrganizationOwnershipTransferTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create(username="transfer_owner", role="ORGANIZATION")
        cls.successor = User.objects.create(username="transfer_successor", role="ATHLETE")
        cls.outsider = User.objects.create(username="transfer_outsider", role="ADMIN", is_staff=True, is_superuser=True)
        cls.organization = Organization.objects.create(user=cls.owner, name="Transfer Team", country="GH")
        cls.owner_membership = OrganizationMembership.objects.create(
            organization=cls.organization, user=cls.owner, role="OWNER",
        )
        cls.membership = OrganizationMembership.objects.create(
            organization=cls.organization, user=cls.successor, role="VIEWER",
        )
        cls.other_organization = Organization.objects.create(user=cls.outsider, name="Other Transfer Team", country="GH")
        cls.other_membership = OrganizationMembership.objects.create(
            organization=cls.other_organization, user=cls.successor, role="RECRUITER",
        )

    def transfer(self, **kwargs):
        params = dict(organization=self.organization, actor=self.owner, membership=self.membership)
        params.update(kwargs)
        return transfer_organization_ownership(**params)

    def assert_original_ownership(self):
        self.organization.refresh_from_db()
        self.owner_membership.refresh_from_db()
        self.membership.refresh_from_db()
        self.assertEqual(self.organization.user_id, self.owner.pk)
        self.assertEqual((self.owner_membership.role, self.owner_membership.status), ("OWNER", "ACTIVE"))
        self.assertEqual(self.membership.role, "VIEWER")
        self.assertEqual(self.organization.memberships.filter(role="OWNER", status="ACTIVE").count(), 1)

    def test_transfer_demotes_promotes_and_updates_owner_link(self):
        result = self.transfer(membership=self.membership.pk)
        self.assertEqual(result.user_id, self.successor.pk)
        self.owner_membership.refresh_from_db()
        self.membership.refresh_from_db()
        self.assertEqual((self.owner_membership.role, self.owner_membership.status), ("MANAGER", "ACTIVE"))
        self.assertEqual((self.membership.role, self.membership.status), ("OWNER", "ACTIVE"))
        self.assertEqual(self.organization.memberships.filter(role="OWNER", status="ACTIVE").count(), 1)
        self.assertEqual(get_organization_role(self.owner, self.organization), "MANAGER")
        self.assertEqual(get_organization_role(self.successor, self.organization), "OWNER")

    def test_all_active_team_roles_can_receive_ownership(self):
        for role in ("MANAGER", "RECRUITER", "VIEWER"):
            OrganizationMembership.objects.filter(pk=self.membership.pk).update(role=role)
            self.transfer()
            self.assertEqual(get_organization_role(self.successor, self.organization), "OWNER")
            self.transfer(actor=self.successor, membership=self.owner_membership)
            self.assertEqual(get_organization_role(self.owner, self.organization), "OWNER")

    def test_nonowners_anonymous_and_platform_admins_are_denied(self):
        for actor in (self.successor, self.outsider, AnonymousUser(), None):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                self.transfer(actor=actor)
        self.assert_original_ownership()

    def test_stale_owner_membership_and_legacy_link_cannot_authorize_transfer(self):
        for status in ("REMOVED", "SUSPENDED"):
            OrganizationMembership.objects.filter(pk=self.owner_membership.pk).update(status=status)
            with self.assertRaises(PermissionDenied):
                self.transfer()
        OrganizationMembership.objects.filter(pk=self.owner_membership.pk).update(role="MANAGER", status="ACTIVE")
        with self.assertRaises(PermissionDenied):
            self.transfer()

    def test_legacy_owner_without_explicit_membership_is_denied(self):
        self.owner_membership.delete()
        with self.assertRaises(PermissionDenied):
            self.transfer()

    def test_inactive_owner_or_organization_is_denied(self):
        User.objects.filter(pk=self.owner.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.transfer()
        User.objects.filter(pk=self.owner.pk).update(is_active=True)
        for status in ("INACTIVE", "MERGED", "CLOSED"):
            Organization.objects.filter(pk=self.organization.pk).update(status=status)
            with self.assertRaises(PermissionDenied):
                self.transfer()

    def test_self_transfer_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.transfer(membership=self.owner_membership)
        self.assert_original_ownership()

    def test_foreign_missing_and_tampered_memberships_are_rejected(self):
        self.other_membership.organization_id = self.organization.pk
        for target in (self.other_membership, self.other_membership.pk, 999999):
            with self.assertRaises(ValidationError):
                self.transfer(membership=target)
        self.assert_original_ownership()

    def test_removed_suspended_and_disabled_successors_are_rejected(self):
        for status in ("REMOVED", "SUSPENDED"):
            OrganizationMembership.objects.filter(pk=self.membership.pk).update(status=status)
            with self.assertRaises(ValidationError):
                self.transfer()
        OrganizationMembership.objects.filter(pk=self.membership.pk).update(status="ACTIVE")
        User.objects.filter(pk=self.successor.pk).update(is_active=False)
        with self.assertRaises(ValidationError):
            self.transfer()
        self.assert_original_ownership()

    def test_successor_linked_to_other_organization_is_rejected_without_changes(self):
        Organization.objects.filter(pk=self.other_organization.pk).update(user=self.successor)
        before = list(Organization.objects.order_by("pk").values())
        with self.assertRaises(ValidationError):
            self.transfer()
        self.assertEqual(list(Organization.objects.order_by("pk").values()), before)
        self.assert_original_ownership()

    def test_global_user_roles_and_other_memberships_are_preserved(self):
        users = list(User.objects.order_by("pk").values())
        other_members = list(self.other_organization.memberships.order_by("pk").values())
        other_org = Organization.objects.get(pk=self.other_organization.pk).__dict__.copy()
        self.transfer()
        self.assertEqual(list(User.objects.order_by("pk").values()), users)
        self.assertEqual(list(self.other_organization.memberships.order_by("pk").values()), other_members)
        self.assertEqual(Organization.objects.get(pk=self.other_organization.pk).user_id, other_org["user_id"])

    def test_former_owner_cannot_repeat_transfer_using_cached_objects(self):
        self.transfer()
        with self.assertRaises(PermissionDenied):
            self.transfer()
        self.assertEqual(get_organization_role(self.successor, self.organization), "OWNER")

    def test_current_membership_owner_is_authoritative_over_stale_organization_link(self):
        Organization.objects.filter(pk=self.organization.pk).update(user=None)
        self.assertEqual(self.transfer().user_id, self.successor.pk)

    def test_promotion_failure_rolls_back_old_owner_demotion(self):
        original_save = OrganizationMembership.save

        def fail_promotion(member, *args, **kwargs):
            original_save(member, *args, **kwargs)
            if member.pk == self.membership.pk:
                raise IntegrityError("Promotion failed")

        with patch.object(OrganizationMembership, "save", fail_promotion):
            with self.assertRaises(IntegrityError):
                self.transfer()
        self.assert_original_ownership()

    def test_owner_link_failure_rolls_back_both_membership_changes(self):
        original_save = Organization.save

        def fail_link(organization, *args, **kwargs):
            original_save(organization, *args, **kwargs)
            raise IntegrityError("Owner link failed")

        with patch.object(Organization, "save", fail_link):
            with self.assertRaises(IntegrityError):
                self.transfer()
        self.assert_original_ownership()


class OrganizationOwnershipTransferConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.owner = User.objects.create(username="race_transfer_owner")
        self.first = User.objects.create(username="race_transfer_first")
        self.second = User.objects.create(username="race_transfer_second")
        self.organization = Organization.objects.create(user=self.owner, name="Race Transfer Team", country="GH")
        self.owner_membership = OrganizationMembership.objects.create(organization=self.organization, user=self.owner, role="OWNER")
        self.first_membership = OrganizationMembership.objects.create(organization=self.organization, user=self.first, role="MANAGER")
        self.second_membership = OrganizationMembership.objects.create(organization=self.organization, user=self.second, role="VIEWER")

    def race(self, *operations):
        barrier = Barrier(len(operations))

        def run(operation):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                for attempt in range(20):
                    try:
                        return operation()
                    except (PermissionDenied, ValidationError):
                        return None
                    except OperationalError as error:
                        if connection.vendor != "sqlite" or "locked" not in str(error).lower() or attempt == 19:
                            raise
                        # Retry only the entire rolled-back transaction.
                        sleep(0.01 * (attempt + 1))
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=len(operations)) as pool:
            futures = [pool.submit(run, operation) for operation in operations]
            return [future.result(timeout=20) for future in futures]

    def transfer(self, membership):
        return transfer_organization_ownership(organization=self.organization, actor=self.owner, membership=membership)

    def assert_consistent_owner(self, organization=None):
        organization = organization or self.organization
        organization.refresh_from_db()
        owners = list(organization.memberships.filter(role="OWNER", status="ACTIVE"))
        self.assertEqual(len(owners), 1)
        self.assertEqual(owners[0].user_id, organization.user_id)

    def test_concurrent_transfers_to_different_members_only_one_succeeds(self):
        results = self.race(lambda: self.transfer(self.first_membership), lambda: self.transfer(self.second_membership))
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assert_consistent_owner()
        self.owner_membership.refresh_from_db()
        self.assertEqual(self.owner_membership.role, "MANAGER")

    def test_concurrent_transfers_to_same_member_only_one_succeeds(self):
        results = self.race(lambda: self.transfer(self.first_membership), lambda: self.transfer(self.first_membership))
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assert_consistent_owner()

    def test_transfer_and_successor_suspension_only_one_succeeds(self):
        results = self.race(
            lambda: self.transfer(self.first_membership),
            lambda: suspend_team_member(organization=self.organization, actor=self.owner, membership=self.first_membership),
        )
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assert_consistent_owner()
        self.first_membership.refresh_from_db()
        self.assertIn((self.first_membership.role, self.first_membership.status), (("OWNER", "ACTIVE"), ("MANAGER", "SUSPENDED")))

    def test_transfer_and_successor_removal_only_one_succeeds(self):
        results = self.race(
            lambda: self.transfer(self.first_membership),
            lambda: remove_team_member(organization=self.organization, actor=self.owner, membership=self.first_membership),
        )
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assert_consistent_owner()

    def test_two_organizations_cannot_transfer_owner_link_to_same_account(self):
        other_owner = User.objects.create(username="race_transfer_other_owner")
        other = Organization.objects.create(user=other_owner, name="Other Race Team", country="GH")
        OrganizationMembership.objects.create(organization=other, user=other_owner, role="OWNER")
        target = OrganizationMembership.objects.create(organization=other, user=self.first, role="RECRUITER")
        results = self.race(
            lambda: self.transfer(self.first_membership),
            lambda: transfer_organization_ownership(organization=other, actor=other_owner, membership=target),
        )
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assert_consistent_owner()
        self.assert_consistent_owner(other)
        self.assertEqual(Organization.objects.filter(user=self.first).count(), 1)

from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.test import TestCase

from accounts.models import User
from .models import Organization, OrganizationMembership
from .services import (
    change_team_member_role, list_team_members, remove_team_member,
    restore_team_member, suspend_team_member,
)


class OrganizationTeamMemberServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create(username="manage_team_owner", role="ORGANIZATION")
        cls.user = User.objects.create(username="manage_team_member", role="ATHLETE")
        cls.other_owner = User.objects.create(username="manage_other_owner", role="SCOUT")
        cls.organization = Organization.objects.create(user=cls.owner, name="Managed Team", country="GH")
        cls.other_organization = Organization.objects.create(user=cls.other_owner, name="Other Team", country="GH")
        cls.owner_membership = OrganizationMembership.objects.create(
            organization=cls.organization, user=cls.owner, role="OWNER",
        )
        cls.membership = OrganizationMembership.objects.create(
            organization=cls.organization, user=cls.user, role="RECRUITER",
        )
        cls.other_membership = OrganizationMembership.objects.create(
            organization=cls.other_organization, user=cls.user, role="MANAGER",
        )
        OrganizationMembership.objects.create(
            organization=cls.other_organization, user=cls.other_owner, role="OWNER",
        )

    def call(self, service, **kwargs):
        params = dict(organization=self.organization, actor=self.owner)
        if service != list_team_members:
            params["membership"] = self.membership
        if service == change_team_member_role:
            params["role"] = "MANAGER"
        params.update(kwargs)
        return service(**params)

    @property
    def services(self):
        return (list_team_members, change_team_member_role, suspend_team_member,
                restore_team_member, remove_team_member)

    def test_list_is_scoped_includes_all_statuses_and_is_read_only(self):
        for status in ("ACTIVE", "SUSPENDED", "REMOVED"):
            OrganizationMembership.objects.filter(pk=self.membership.pk).update(status=status)
            before = list(OrganizationMembership.objects.order_by("pk").values())
            members = self.call(list_team_members)
            self.assertIsInstance(members, list)
            self.assertEqual([member.pk for member in members], [self.owner_membership.pk, self.membership.pk])
            self.assertEqual(members[1].status, status)
            self.assertEqual(list(OrganizationMembership.objects.order_by("pk").values()), before)

    def test_role_change_supports_all_team_roles_and_preserves_status(self):
        for status in ("ACTIVE", "SUSPENDED"):
            OrganizationMembership.objects.filter(pk=self.membership.pk).update(status=status)
            for role in ("MANAGER", "RECRUITER", "VIEWER"):
                result = self.call(change_team_member_role, role=role)
                self.assertEqual((result.role, result.status), (role, status))
                self.membership.refresh_from_db()
                self.assertEqual(self.membership.role, role)

    def test_invalid_role_and_owner_promotion_are_rejected(self):
        for role in ("OWNER", "ADMIN", "manager", "", None):
            with self.subTest(role=role), self.assertRaises(ValidationError):
                self.call(change_team_member_role, role=role)
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.role, "RECRUITER")

    def test_suspend_restore_and_soft_remove_preserve_membership_id_and_role(self):
        for service, expected in (
            (suspend_team_member, "SUSPENDED"), (restore_team_member, "ACTIVE"),
            (remove_team_member, "REMOVED"), (restore_team_member, "ACTIVE"),
        ):
            result = self.call(service, membership=self.membership.pk)
            self.assertEqual(result.pk, self.membership.pk)
            self.assertEqual((result.role, result.status), ("RECRUITER", expected))
            self.assertEqual(self.organization.memberships.count(), 2)

    def test_removal_also_works_for_suspended_member(self):
        self.call(suspend_team_member)
        result = self.call(remove_team_member)
        self.assertEqual(result.status, "REMOVED")

    def test_removed_members_cannot_be_suspended_or_have_role_changed(self):
        self.call(remove_team_member)
        for service in (suspend_team_member, change_team_member_role):
            with self.assertRaises(ValidationError):
                self.call(service)
        self.membership.refresh_from_db()
        self.assertEqual((self.membership.role, self.membership.status), ("RECRUITER", "REMOVED"))

    def test_repeated_actions_are_idempotent_without_timestamp_changes(self):
        for service in (suspend_team_member, restore_team_member, remove_team_member):
            first = self.call(service)
            second = self.call(service)
            self.assertEqual((first.status, first.updated_at), (second.status, second.updated_at))
        self.call(restore_team_member)
        first = self.call(change_team_member_role)
        second = self.call(change_team_member_role)
        self.assertEqual(first.updated_at, second.updated_at)

    def test_sole_active_owner_cannot_be_demoted_suspended_or_removed(self):
        for service in (change_team_member_role, suspend_team_member, remove_team_member):
            with self.subTest(service=service.__name__), self.assertRaises(ValidationError):
                self.call(service, membership=self.owner_membership)
            self.owner_membership.refresh_from_db()
            self.assertEqual((self.owner_membership.role, self.owner_membership.status), ("OWNER", "ACTIVE"))

    def test_owner_role_and_active_status_noops_are_allowed(self):
        self.assertEqual(self.call(change_team_member_role, membership=self.owner_membership, role="OWNER").role, "OWNER")
        self.assertEqual(self.call(restore_team_member, membership=self.owner_membership).status, "ACTIVE")

    def test_inactive_owner_cannot_be_restored_over_current_active_owner(self):
        for status in ("SUSPENDED", "REMOVED"):
            OrganizationMembership.objects.filter(pk=self.membership.pk).update(role="OWNER", status=status)
            with self.assertRaises(ValidationError):
                self.call(restore_team_member)
            self.membership.refresh_from_db()
            self.assertEqual((self.membership.role, self.membership.status), ("OWNER", status))
        # A removed former owner can first be restored as a team member through
        # the invitation workflow; a suspended former owner can be demoted here.
        OrganizationMembership.objects.filter(pk=self.membership.pk).update(status="SUSPENDED")
        self.call(change_team_member_role, role="VIEWER")
        self.assertEqual(self.call(restore_team_member).role, "VIEWER")

    def test_foreign_membership_objects_and_ids_are_rejected(self):
        before = list(OrganizationMembership.objects.order_by("pk").values())
        for service in self.services[1:]:
            for target in (self.other_membership, self.other_membership.pk, 999999):
                with self.subTest(service=service.__name__, target=target), self.assertRaises(ValidationError):
                    self.call(service, membership=target)
        self.assertEqual(list(OrganizationMembership.objects.order_by("pk").values()), before)

    def test_stale_or_tampered_membership_object_does_not_override_database_scope(self):
        self.other_membership.organization_id = self.organization.pk
        with self.assertRaises(ValidationError):
            self.call(remove_team_member, membership=self.other_membership)

    def test_nonowners_and_platform_admin_cannot_list_or_manage(self):
        for role in ("MANAGER", "RECRUITER", "VIEWER"):
            OrganizationMembership.objects.filter(pk=self.membership.pk).update(role=role)
            for service in self.services:
                with self.subTest(role=role, service=service.__name__), self.assertRaises(PermissionDenied):
                    self.call(service, actor=self.user)
        self.other_owner.is_superuser = self.other_owner.is_staff = True
        self.other_owner.save()
        for service in self.services:
            for actor in (self.other_owner, AnonymousUser(), None):
                with self.assertRaises(PermissionDenied):
                    self.call(service, actor=actor)

    def test_stale_owner_objects_and_legacy_link_do_not_bypass_membership(self):
        for status in ("SUSPENDED", "REMOVED"):
            OrganizationMembership.objects.filter(pk=self.owner_membership.pk).update(status=status)
            for service in self.services:
                with self.assertRaises(PermissionDenied):
                    self.call(service)
        OrganizationMembership.objects.filter(pk=self.owner_membership.pk).update(role="VIEWER", status="ACTIVE")
        for service in self.services:
            with self.assertRaises(PermissionDenied):
                self.call(service)

    def test_inactive_owner_and_organization_are_denied_using_current_state(self):
        User.objects.filter(pk=self.owner.pk).update(is_active=False)
        for service in self.services:
            with self.assertRaises(PermissionDenied):
                self.call(service)
        User.objects.filter(pk=self.owner.pk).update(is_active=True)
        for status in ("INACTIVE", "MERGED", "CLOSED"):
            Organization.objects.filter(pk=self.organization.pk).update(status=status)
            for service in self.services:
                with self.assertRaises(PermissionDenied):
                    self.call(service)

    def test_current_owner_membership_is_authoritative_over_legacy_link(self):
        OrganizationMembership.objects.filter(pk=self.owner_membership.pk).update(status="REMOVED")
        OrganizationMembership.objects.filter(pk=self.membership.pk).update(role="OWNER")
        self.assertEqual(len(self.call(list_team_members, actor=self.user)), 2)
        with self.assertRaises(ValidationError):
            self.call(restore_team_member, actor=self.user, membership=self.owner_membership)
        member = OrganizationMembership.objects.create(
            organization=self.organization, user=self.other_owner, role="MANAGER",
        )
        result = self.call(suspend_team_member, actor=self.user, membership=member)
        self.assertEqual(result.status, "SUSPENDED")
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.user_id, self.owner.pk)

    def test_all_actions_preserve_accounts_other_memberships_and_organization_links(self):
        users = list(User.objects.order_by("pk").values())
        organizations = list(Organization.objects.order_by("pk").values())
        other_memberships = list(self.other_organization.memberships.order_by("pk").values())
        for service in (list_team_members, change_team_member_role, suspend_team_member,
                        remove_team_member, restore_team_member):
            self.call(service)
            self.assertEqual(list(User.objects.order_by("pk").values()), users)
            self.assertEqual(list(Organization.objects.order_by("pk").values()), organizations)
            self.assertEqual(list(self.other_organization.memberships.order_by("pk").values()), other_memberships)

    def test_database_failure_rolls_back_each_member_mutation(self):
        original_save = OrganizationMembership.save

        def save_then_fail(member, *args, **kwargs):
            original_save(member, *args, **kwargs)
            raise IntegrityError("Failure after membership write")

        for service in self.services[1:]:
            initial_status = "SUSPENDED" if service == restore_team_member else "ACTIVE"
            OrganizationMembership.objects.filter(pk=self.membership.pk).update(status=initial_status)
            before = OrganizationMembership.objects.get(pk=self.membership.pk)
            with patch.object(OrganizationMembership, "save", save_then_fail):
                with self.assertRaises(IntegrityError):
                    self.call(service)
            self.membership.refresh_from_db()
            self.assertEqual((self.membership.role, self.membership.status, self.membership.updated_at),
                             (before.role, before.status, before.updated_at))

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.test import TestCase

from accounts.models import User

from .models import Organization, OrganizationMembership
from .permissions import (
    OrganizationCapability as Capability,
    get_organization_capabilities,
    get_organization_role,
    has_organization_capability,
    require_organization_capability,
)


class OrganizationCapabilityPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.legacy_owner = User.objects.create_user(
            username="permission_legacy_owner", role="ORGANIZATION",
        )
        cls.organization = Organization.objects.create(
            user=cls.legacy_owner, name="Permission Organization", country="GH",
        )
        cls.other_owner = User.objects.create_user(
            username="permission_other_owner", role="ORGANIZATION",
        )
        cls.other_organization = Organization.objects.create(
            user=cls.other_owner, name="Other Permission Organization", country="GH",
        )
        cls.member = User.objects.create_user(
            username="permission_member", role="ATHLETE",
        )
        cls.outsider = User.objects.create_user(username="permission_outsider")
        cls.admin = User.objects.create_user(
            username="permission_platform_admin", role="ADMIN", is_superuser=True, is_staff=True,
        )

    def membership(self, role="VIEWER", status="ACTIVE", user=None):
        return OrganizationMembership.objects.create(
            organization=self.organization, user=user or self.member,
            role=role, status=status,
        )

    def assert_denied(self, user, organization=None):
        organization = self.organization if organization is None else organization
        self.assertIsNone(get_organization_role(user, organization))
        self.assertEqual(get_organization_capabilities(user, organization), frozenset())
        for capability in Capability:
            self.assertFalse(has_organization_capability(user, organization, capability))
        with self.assertRaises(PermissionDenied):
            require_organization_capability(user, organization, Capability.VIEW_DASHBOARD)

    def test_role_capability_matrix_is_enforced_for_members_without_org_account_role(self):
        read_capabilities = {
            Capability.VIEW_PROFILE, Capability.VIEW_DASHBOARD, Capability.VIEW_TALENTS,
            Capability.VIEW_OPPORTUNITIES, Capability.VIEW_RECRUITMENT,
            Capability.VIEW_EVENTS, Capability.VIEW_COMPETITIONS, Capability.VIEW_ANALYTICS,
            Capability.VIEW_ADVERTISING, Capability.VIEW_POSTS, Capability.VIEW_MEMBERS,
        }
        recruitment_capabilities = {
            Capability.MANAGE_RECRUITMENT, Capability.MANAGE_OPPORTUNITIES,
        }
        operational_capabilities = recruitment_capabilities | {
            Capability.EDIT_PROFILE, Capability.MANAGE_EVENTS, Capability.MANAGE_COMPETITIONS,
            Capability.MANAGE_ADVERTISING, Capability.MANAGE_POSTS,
            Capability.MANAGE_AGREEMENTS,
        }
        expected = {
            "OWNER": set(Capability),
            "MANAGER": read_capabilities | operational_capabilities,
            "RECRUITER": read_capabilities | recruitment_capabilities,
            "VIEWER": read_capabilities,
        }
        membership = self.membership()
        for role, allowed in expected.items():
            OrganizationMembership.objects.filter(pk=membership.pk).update(role=role)
            with self.subTest(role=role):
                self.assertEqual(get_organization_role(self.member, self.organization), role)
                for capability in Capability:
                    self.assertEqual(
                        has_organization_capability(self.member, self.organization, capability),
                        capability in allowed,
                        f"{role}: {capability.value}",
                    )
                    if capability in allowed:
                        self.assertEqual(
                            require_organization_capability(
                                self.member, self.organization, capability.value,
                            ),
                            role,
                        )
                    else:
                        with self.assertRaises(PermissionDenied):
                            require_organization_capability(
                                self.member, self.organization, capability,
                            )
        self.member.refresh_from_db()
        self.assertEqual(self.member.role, "ATHLETE")

    def test_active_membership_is_required_for_every_role(self):
        membership = self.membership()
        for role in ("OWNER", "MANAGER", "RECRUITER", "VIEWER"):
            for status in ("REMOVED", "SUSPENDED"):
                with self.subTest(role=role, status=status):
                    OrganizationMembership.objects.filter(pk=membership.pk).update(
                        role=role, status=status,
                    )
                    self.assert_denied(self.member)

    def test_all_non_active_organization_statuses_deny_every_membership_role(self):
        membership = self.membership()
        for role in ("OWNER", "MANAGER", "RECRUITER", "VIEWER"):
            OrganizationMembership.objects.filter(pk=membership.pk).update(role=role)
            for status in ("INACTIVE", "MERGED", "CLOSED", "UNKNOWN"):
                with self.subTest(role=role, status=status):
                    Organization.objects.filter(pk=self.organization.pk).update(status=status)
                    self.assert_denied(self.member)

    def test_legacy_owner_compatibility_is_read_only_and_can_be_disabled(self):
        user_records = list(User.objects.order_by("pk").values())
        organization_records = list(Organization.objects.order_by("pk").values())
        self.assertEqual(
            get_organization_role(self.legacy_owner, self.organization), "OWNER",
        )
        self.assertEqual(
            get_organization_capabilities(self.legacy_owner, self.organization),
            frozenset(Capability),
        )
        self.assertFalse(has_organization_capability(
            self.legacy_owner, self.organization, Capability.MANAGE_MEMBERS,
            allow_legacy_owner=False,
        ))
        self.assertEqual(OrganizationMembership.objects.count(), 0)
        self.assertEqual(list(User.objects.order_by("pk").values()), user_records)
        self.assertEqual(list(Organization.objects.order_by("pk").values()), organization_records)

    def test_suspended_or_removed_legacy_owner_membership_cannot_use_fallback(self):
        membership = self.membership(role="OWNER", user=self.legacy_owner)
        for status in ("REMOVED", "SUSPENDED"):
            with self.subTest(status=status):
                OrganizationMembership.objects.filter(pk=membership.pk).update(status=status)
                self.assert_denied(self.legacy_owner)

    def test_reduced_membership_role_overrides_legacy_ownership(self):
        self.membership(role="VIEWER", user=self.legacy_owner)
        self.assertEqual(get_organization_role(self.legacy_owner, self.organization), "VIEWER")
        self.assertTrue(has_organization_capability(
            self.legacy_owner, self.organization, Capability.VIEW_DASHBOARD,
        ))
        self.assertFalse(has_organization_capability(
            self.legacy_owner, self.organization, Capability.MANAGE_MEMBERS,
        ))
        self.assertFalse(has_organization_capability(
            self.legacy_owner, self.organization, Capability.EDIT_PROFILE,
        ))

    def test_existing_membership_roster_prevents_stale_legacy_owner_fallback(self):
        self.membership(role="OWNER")
        self.assert_denied(self.legacy_owner)
        self.assertEqual(get_organization_role(self.member, self.organization), "OWNER")

    def test_roster_with_no_active_owner_does_not_restore_legacy_privileges(self):
        self.membership(role="MANAGER")
        self.assert_denied(self.legacy_owner)
        self.assertEqual(get_organization_role(self.member, self.organization), "MANAGER")

    def test_legacy_owner_is_denied_when_organization_is_inactive(self):
        for status in ("INACTIVE", "MERGED", "CLOSED"):
            with self.subTest(status=status):
                Organization.objects.filter(pk=self.organization.pk).update(status=status)
                self.assert_denied(self.legacy_owner)

    def test_membership_does_not_grant_access_to_another_organization(self):
        self.membership(role="OWNER")
        self.assert_denied(self.member, self.other_organization)
        self.assert_denied(self.outsider)
        self.assert_denied(self.other_owner)

    def test_platform_admin_flags_and_account_roles_do_not_bypass_membership(self):
        self.assert_denied(self.admin)
        unlinked = User.objects.create_user(
            username="unlinked_permission_org", role="ORGANIZATION",
        )
        self.assert_denied(unlinked)

    def test_anonymous_none_unsaved_users_and_ownerless_orgs_are_denied(self):
        for user in (AnonymousUser(), None, User(username="unsaved")):
            with self.subTest(user=user):
                self.assert_denied(user)
        organization = Organization.objects.create(name="Ownerless", country="GH")
        self.assert_denied(self.outsider, organization)

    def test_invalid_capability_and_organization_identifiers_fail_closed(self):
        for capability in ("unknown", "OWNER", None, [], {}):
            with self.subTest(capability=capability):
                self.assertFalse(has_organization_capability(
                    self.legacy_owner, self.organization, capability,
                ))
                with self.assertRaises(PermissionDenied):
                    require_organization_capability(
                        self.legacy_owner, self.organization, capability,
                    )
        for organization in (None, "not-an-id", [], 999999, Organization(name="Unsaved")):
            with self.subTest(organization=organization):
                self.assertIsNone(get_organization_role(self.legacy_owner, organization))
        self.assertEqual(
            get_organization_role(self.legacy_owner, self.organization.pk), "OWNER",
        )

    def test_permissions_read_current_membership_and_org_state_instead_of_cached_objects(self):
        membership = self.membership(role="MANAGER")
        self.assertTrue(has_organization_capability(
            self.member, self.organization, Capability.MANAGE_EVENTS,
        ))
        OrganizationMembership.objects.filter(pk=membership.pk).update(role="VIEWER")
        self.assertEqual(membership.role, "MANAGER")
        self.assertFalse(has_organization_capability(
            self.member, self.organization, Capability.MANAGE_EVENTS,
        ))
        OrganizationMembership.objects.filter(pk=membership.pk).update(status="SUSPENDED")
        self.assert_denied(self.member)
        OrganizationMembership.objects.filter(pk=membership.pk).update(
            role="MANAGER", status="ACTIVE",
        )
        Organization.objects.filter(pk=self.organization.pk).update(status="INACTIVE")
        self.assertEqual(self.organization.status, "ACTIVE")
        self.assert_denied(self.member)
        Organization.objects.filter(pk=self.organization.pk).update(status="ACTIVE")
        self.assertTrue(has_organization_capability(
            self.member, self.organization, Capability.MANAGE_EVENTS,
        ))

    def test_disabled_and_deleted_accounts_cannot_use_membership_or_legacy_ownership(self):
        self.membership(role="OWNER")
        for user in (self.member, self.legacy_owner):
            with self.subTest(user=user.username):
                User.objects.filter(pk=user.pk).update(is_active=False)
                self.assertTrue(user.is_active)
                self.assert_denied(user)
        User.objects.filter(pk=self.member.pk).delete()
        self.assert_denied(self.member)

    def test_explicit_owner_membership_works_without_legacy_owner_link(self):
        Organization.objects.filter(pk=self.organization.pk).update(user=None)
        self.membership(role="OWNER")
        self.assertEqual(get_organization_role(self.member, self.organization), "OWNER")
        self.organization.refresh_from_db()
        self.assertIsNone(self.organization.user_id)

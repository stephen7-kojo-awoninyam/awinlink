from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.models import User

from .models import Organization, OrganizationMembership


class OrganizationMembershipConstraintTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="membership_owner", role="ORGANIZATION")
        cls.organization = Organization.objects.create(
            user=cls.owner, name="Membership Organization", country="GH",
        )
        cls.owner_membership = OrganizationMembership.objects.create(
            organization=cls.organization, user=cls.owner, role="OWNER", status="ACTIVE",
        )

    def member(self, username, role="VIEWER", status="ACTIVE"):
        return OrganizationMembership(
            organization=self.organization,
            user=User.objects.create_user(username=username),
            role=role, status=status,
        )

    def test_organization_user_pair_is_unique_across_roles_and_statuses(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            OrganizationMembership.objects.create(
                organization=self.organization, user=self.owner,
                role="MANAGER", status="REMOVED",
            )
        self.assertEqual(self.organization.memberships.count(), 1)

    def test_bulk_insert_cannot_create_a_second_active_owner(self):
        candidate = self.member("second_owner", role="OWNER")
        with self.assertRaises(IntegrityError), transaction.atomic():
            OrganizationMembership.objects.bulk_create([candidate])
        self.assertEqual(
            self.organization.memberships.filter(role="OWNER", status="ACTIVE").count(), 1,
        )

    def test_all_team_roles_can_be_active_alongside_the_owner(self):
        for role in ("MANAGER", "RECRUITER", "VIEWER"):
            self.member(f"member_{role.lower()}", role=role).save()
        self.assertEqual(self.organization.memberships.filter(status="ACTIVE").count(), 4)

    def test_suspended_and_removed_owner_memberships_do_not_occupy_active_owner_slot(self):
        for status in ("REMOVED", "SUSPENDED"):
            self.member(f"owner_{status.lower()}", role="OWNER", status=status).save()
        self.assertEqual(self.organization.memberships.filter(role="OWNER").count(), 3)
        self.assertEqual(
            self.organization.memberships.filter(role="OWNER", status="ACTIVE").count(), 1,
        )

    def test_bulk_update_cannot_reactivate_a_second_owner(self):
        candidate = self.member("suspended_owner", role="OWNER", status="SUSPENDED")
        candidate.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            OrganizationMembership.objects.filter(pk=candidate.pk).update(status="ACTIVE")
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, "SUSPENDED")

    def test_bulk_update_cannot_promote_a_second_active_owner(self):
        candidate = self.member("manager", role="MANAGER")
        candidate.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            OrganizationMembership.objects.filter(pk=candidate.pk).update(role="OWNER")
        candidate.refresh_from_db()
        self.assertEqual(candidate.role, "MANAGER")

    def test_ownership_can_transfer_atomically_without_changing_legacy_user(self):
        candidate = self.member("future_owner", role="MANAGER")
        candidate.save()
        with transaction.atomic():
            OrganizationMembership.objects.filter(pk=self.owner_membership.pk).update(
                status="REMOVED",
            )
            OrganizationMembership.objects.filter(pk=candidate.pk).update(role="OWNER")
        self.assertEqual(
            self.organization.memberships.get(role="OWNER", status="ACTIVE").pk,
            candidate.pk,
        )
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.user_id, self.owner.pk)

    def test_same_user_can_belong_to_multiple_organizations(self):
        other = Organization.objects.create(name="Other Organization", country="GH")
        OrganizationMembership.objects.create(
            organization=other, user=self.owner, role="OWNER",
        )
        self.assertEqual(self.owner.organization_memberships.count(), 2)

    def test_database_rejects_unknown_roles_and_statuses(self):
        for role in ("ADMIN", "owner", ""):
            candidate = self.member(f"bad_role_{role or 'empty'}", role=role)
            with self.subTest(role=role), self.assertRaises(IntegrityError), transaction.atomic():
                candidate.save()
        for status in ("INACTIVE", "active", ""):
            candidate = self.member(f"bad_status_{status or 'empty'}", status=status)
            with self.subTest(status=status), self.assertRaises(IntegrityError), transaction.atomic():
                candidate.save()

    def test_account_and_organization_suspension_do_not_weaken_owner_constraint(self):
        self.owner.is_active = False
        self.owner.save(update_fields=["is_active"])
        self.organization.status = "INACTIVE"
        self.organization.save(update_fields=["status"])
        candidate = self.member("inactive_org_second_owner", role="OWNER")
        with self.assertRaises(IntegrityError), transaction.atomic():
            candidate.save()
        self.owner.refresh_from_db()
        self.organization.refresh_from_db()
        self.assertFalse(self.owner.is_active)
        self.assertEqual(self.organization.user_id, self.owner.pk)

    def test_removing_membership_does_not_delete_organization_or_user(self):
        self.owner_membership.delete()
        self.organization.refresh_from_db()
        self.owner.refresh_from_db()
        self.assertEqual(self.organization.user_id, self.owner.pk)
        self.assertTrue(self.owner.is_active)

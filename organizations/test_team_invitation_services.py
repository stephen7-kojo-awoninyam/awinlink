from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from time import sleep
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, OperationalError, close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from accounts.models import User
from .models import Organization, OrganizationMembership, OrganizationTeamInvitation
from .permissions import get_organization_role
from .services import (
    accept_team_invitation, create_team_invitation,
    decline_team_invitation, revoke_team_invitation,
)


class OrganizationTeamInvitationServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create(username="invite_owner", role="ORGANIZATION")
        cls.recipient = User.objects.create(username="invite_recipient")
        cls.outsider = User.objects.create(username="invite_outsider")
        cls.organization = Organization.objects.create(
            user=cls.owner, name="Invitation Organization", country="GH",
        )
        cls.owner_membership = OrganizationMembership.objects.create(
            organization=cls.organization, user=cls.owner, role="OWNER",
        )

    def create(self, **kwargs):
        params = dict(organization=self.organization, inviter=self.owner, recipient=self.recipient)
        params.update(kwargs)
        return create_team_invitation(**params)

    def accept(self, invitation, token, **kwargs):
        params = dict(invitation=invitation, recipient=self.recipient, token=token)
        params.update(kwargs)
        return accept_team_invitation(**params)

    def membership(self, **kwargs):
        params = dict(organization=self.organization, user=self.recipient)
        params.update(kwargs)
        return OrganizationMembership.objects.create(**params)

    def assert_pending(self, invitation):
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "PENDING")

    def test_create_stores_only_hash_and_returns_token_once(self):
        invitation, token = self.create(role="RECRUITER")
        stored = OrganizationTeamInvitation.objects.get(pk=invitation.pk)
        self.assertNotEqual(stored.token_hash, token)
        self.assertTrue(stored.check_token(token))
        self.assertNotIn(token, str(stored.__dict__))
        self.assertEqual(stored.inviter_id, self.owner.pk)
        self.assertEqual(stored.recipient_id, self.recipient.pk)
        self.assertEqual(stored.role, "RECRUITER")
        self.assertGreater(stored.expires_at, timezone.now())
        self.assertEqual(OrganizationMembership.objects.count(), 1)

    def test_duplicate_pending_invite_is_rejected_across_roles(self):
        invitation, token = self.create()
        with self.assertRaises(ValidationError):
            self.create(role="MANAGER")
        self.assertEqual(OrganizationTeamInvitation.objects.count(), 1)
        self.assertTrue(invitation.check_token(token))

    def test_expired_pending_invite_is_closed_before_replacement(self):
        old, token = self.create()
        OrganizationTeamInvitation.objects.filter(pk=old.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        new, new_token = self.create()
        old.refresh_from_db()
        self.assertEqual(old.status, "EXPIRED")
        self.assertFalse(old.check_token(token))
        self.assertTrue(new.check_token(new_token))
        self.assertEqual(self.organization.team_invitations.filter(status="PENDING").count(), 1)

    def test_create_requires_owner_not_manager_recruiter_viewer_or_admin(self):
        member = self.membership(role="MANAGER")
        for role in ("MANAGER", "RECRUITER", "VIEWER"):
            OrganizationMembership.objects.filter(pk=member.pk).update(role=role)
            with self.subTest(role=role), self.assertRaises(PermissionDenied):
                self.create(inviter=self.recipient, recipient=self.outsider)
        self.outsider.is_superuser = self.outsider.is_staff = True
        self.outsider.save()
        for user in (self.outsider, AnonymousUser()):
            with self.assertRaises(PermissionDenied):
                self.create(inviter=user)
        self.assertFalse(OrganizationTeamInvitation.objects.exists())

    def test_stale_owner_object_cannot_bypass_membership_status(self):
        for status in ("SUSPENDED", "REMOVED"):
            OrganizationMembership.objects.filter(pk=self.owner_membership.pk).update(status=status)
            with self.subTest(status=status), self.assertRaises(PermissionDenied):
                self.create()

    def test_inactive_organization_or_owner_cannot_create(self):
        for status in ("INACTIVE", "CLOSED", "MERGED"):
            Organization.objects.filter(pk=self.organization.pk).update(status=status)
            with self.assertRaises(PermissionDenied):
                self.create()
        Organization.objects.filter(pk=self.organization.pk).update(status="ACTIVE")
        User.objects.filter(pk=self.owner.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.create()

    def test_invalid_and_owner_roles_are_rejected(self):
        for role in ("OWNER", "ADMIN", "viewer", ""):
            with self.subTest(role=role), self.assertRaises(ValidationError):
                self.create(role=role)

    def test_invalid_expiry_is_rejected(self):
        for expiry in (timezone.now(), timezone.now() - timedelta(days=1), timezone.now().replace(tzinfo=None), "tomorrow"):
            with self.subTest(expiry=expiry), self.assertRaises(ValidationError):
                self.create(expires_at=expiry)
        expiry = timezone.now() + timedelta(hours=1)
        invitation, _ = self.create(expires_at=expiry)
        self.assertEqual(invitation.expires_at, expiry)

    def test_inactive_and_unsaved_recipients_are_rejected(self):
        User.objects.filter(pk=self.recipient.pk).update(is_active=False)
        for user in (self.recipient, User(username="unsaved"), AnonymousUser()):
            with self.assertRaises(PermissionDenied):
                self.create(recipient=user)

    def test_active_and_suspended_members_cannot_be_invited(self):
        member = self.membership()
        for status in ("ACTIVE", "SUSPENDED"):
            OrganizationMembership.objects.filter(pk=member.pk).update(status=status)
            with self.assertRaises(ValidationError):
                self.create()
        with self.assertRaises(ValidationError):
            self.create(recipient=self.owner)

    def test_accept_creates_each_team_role_and_consumes_token(self):
        for role in ("MANAGER", "RECRUITER", "VIEWER"):
            recipient = User.objects.create(username=f"invite_{role}")
            invitation, token = self.create(recipient=recipient, role=role)
            accepted = self.accept(invitation, token, recipient=recipient)
            member = OrganizationMembership.objects.get(organization=self.organization, user=recipient)
            self.assertEqual((member.role, member.status), (role, "ACTIVE"))
            self.assertEqual(accepted.status, "ACCEPTED")
            self.assertFalse(accepted.check_token(token))
            with self.assertRaises(ValidationError):
                self.accept(invitation, token, recipient=recipient)
            self.assertEqual(OrganizationMembership.objects.filter(user=recipient).count(), 1)
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.user_id, self.owner.pk)

    def test_accept_reactivates_removed_membership_without_creating_duplicate(self):
        member = self.membership(role="VIEWER", status="REMOVED")
        invitation, token = self.create(role="MANAGER")
        self.accept(invitation, token)
        member.refresh_from_db()
        self.assertEqual((member.role, member.status), ("MANAGER", "ACTIVE"))
        self.assertEqual(OrganizationMembership.objects.filter(user=self.recipient).count(), 1)

    def test_accept_does_not_overwrite_active_or_suspended_membership(self):
        invitation, token = self.create(role="MANAGER")
        member = self.membership(role="RECRUITER")
        for status in ("ACTIVE", "SUSPENDED"):
            OrganizationMembership.objects.filter(pk=member.pk).update(status=status)
            with self.assertRaises(ValidationError):
                self.accept(invitation, token)
            member.refresh_from_db()
            self.assertEqual((member.role, member.status), ("RECRUITER", status))
            self.assert_pending(invitation)

    def test_recipient_identity_and_token_are_required_for_both_responses(self):
        invitation, token = self.create()
        for service in (accept_team_invitation, decline_team_invitation):
            for user, supplied_token in ((self.outsider, token), (AnonymousUser(), token), (self.recipient, "wrong"), (self.recipient, None)):
                with self.subTest(service=service.__name__), self.assertRaises(PermissionDenied):
                    service(invitation=invitation, recipient=user, token=supplied_token)
                self.assert_pending(invitation)
        self.assertEqual(OrganizationMembership.objects.count(), 1)

    def test_disabled_recipient_cannot_respond_using_stale_user_object(self):
        invitation, token = self.create()
        User.objects.filter(pk=self.recipient.pk).update(is_active=False)
        for service in (accept_team_invitation, decline_team_invitation):
            with self.assertRaises(PermissionDenied):
                service(invitation=invitation, recipient=self.recipient, token=token)

    def test_expired_invitation_cannot_accept_decline_or_revoke(self):
        invitation, token = self.create()
        OrganizationTeamInvitation.objects.filter(pk=invitation.pk).update(expires_at=timezone.now())
        for service in (accept_team_invitation, decline_team_invitation):
            with self.assertRaises(ValidationError):
                service(invitation=invitation, recipient=self.recipient, token=token)
        with self.assertRaises(ValidationError):
            revoke_team_invitation(invitation=invitation, actor=self.owner)
        self.assertEqual(OrganizationMembership.objects.count(), 1)

    def test_decline_and_revoke_are_single_use_and_do_not_create_memberships(self):
        for terminal in ("DECLINED", "REVOKED"):
            invitation, token = self.create()
            if terminal == "DECLINED":
                result = decline_team_invitation(invitation=invitation.pk, recipient=self.recipient, token=token)
            else:
                result = revoke_team_invitation(invitation=invitation.pk, actor=self.owner)
            self.assertEqual(result.status, terminal)
            for service in (accept_team_invitation, decline_team_invitation):
                with self.assertRaises(ValidationError):
                    service(invitation=invitation, recipient=self.recipient, token=token)
            with self.assertRaises(ValidationError):
                revoke_team_invitation(invitation=invitation, actor=self.owner)
        self.assertEqual(OrganizationMembership.objects.count(), 1)

    def test_revoke_requires_current_owner(self):
        invitation, _ = self.create()
        member = self.membership(role="MANAGER")
        for user in (self.recipient, self.outsider, AnonymousUser()):
            with self.assertRaises(PermissionDenied):
                revoke_team_invitation(invitation=invitation, actor=user)
        OrganizationMembership.objects.filter(pk=self.owner_membership.pk).update(status="REMOVED")
        OrganizationMembership.objects.filter(pk=member.pk).update(role="OWNER")
        self.assertEqual(revoke_team_invitation(invitation=invitation, actor=self.recipient).status, "REVOKED")

    def test_accept_rechecks_current_inviter_authority_and_org_status(self):
        invitation, token = self.create()
        OrganizationMembership.objects.filter(pk=self.owner_membership.pk).update(role="VIEWER")
        with self.assertRaises(PermissionDenied):
            self.accept(invitation, token)
        OrganizationMembership.objects.filter(pk=self.owner_membership.pk).update(role="OWNER")
        Organization.objects.filter(pk=self.organization.pk).update(status="INACTIVE")
        with self.assertRaises(PermissionDenied):
            self.accept(invitation, token)
        self.assert_pending(invitation)
        self.assertEqual(OrganizationMembership.objects.count(), 1)

    def test_missing_inviter_cannot_authorize_acceptance(self):
        invitation, token = self.create()
        OrganizationTeamInvitation.objects.filter(pk=invitation.pk).update(inviter=None)
        with self.assertRaises(PermissionDenied):
            self.accept(invitation, token)

    def test_owner_role_in_existing_invitation_cannot_bypass_transfer(self):
        invitation, token = self.create()
        OrganizationTeamInvitation.objects.filter(pk=invitation.pk).update(role="OWNER")
        with self.assertRaises(ValidationError):
            self.accept(invitation, token)
        self.assertEqual(self.organization.memberships.filter(role="OWNER", status="ACTIVE").count(), 1)

    def test_other_organization_owner_cannot_create_or_revoke(self):
        other = Organization.objects.create(name="Other Team", country="GH")
        OrganizationMembership.objects.create(organization=other, user=self.outsider, role="OWNER")
        with self.assertRaises(PermissionDenied):
            self.create(inviter=self.outsider)
        invitation, _ = self.create()
        with self.assertRaises(PermissionDenied):
            revoke_team_invitation(invitation=invitation, actor=self.outsider)

    def test_legacy_owner_access_is_preserved_when_first_member_accepts(self):
        self.owner_membership.delete()
        invitation, token = self.create()
        self.assertEqual(OrganizationMembership.objects.count(), 0)
        self.accept(invitation, token)
        self.assertEqual(get_organization_role(self.owner, self.organization), "OWNER")
        self.assertEqual(get_organization_role(self.recipient, self.organization), "VIEWER")
        self.assertEqual(OrganizationMembership.objects.count(), 2)

    def test_accept_rolls_back_new_membership_when_transition_fails(self):
        invitation, token = self.create()
        with patch("organizations.services._transition", side_effect=ValidationError("expired during acceptance")):
            with self.assertRaises(ValidationError):
                self.accept(invitation, token)
        self.assertEqual(OrganizationMembership.objects.count(), 1)
        self.assert_pending(invitation)
        self.assertTrue(invitation.check_token(token))

    def test_accept_rolls_back_reactivation_when_transition_fails(self):
        member = self.membership(status="REMOVED")
        invitation, token = self.create(role="MANAGER")
        with patch("organizations.services._transition", side_effect=ValidationError("closed")):
            with self.assertRaises(ValidationError):
                self.accept(invitation, token)
        member.refresh_from_db()
        self.assertEqual((member.role, member.status), ("VIEWER", "REMOVED"))
        self.assert_pending(invitation)

    def test_membership_database_failure_leaves_invitation_pending(self):
        invitation, token = self.create()
        with patch.object(OrganizationMembership.objects, "create", side_effect=IntegrityError("membership conflict")):
            with self.assertRaises(IntegrityError):
                self.accept(invitation, token)
        self.assert_pending(invitation)
        self.assertEqual(OrganizationMembership.objects.count(), 1)

    def test_failed_replacement_rolls_back_expiration_of_previous_invitation(self):
        invitation, _ = self.create()
        OrganizationTeamInvitation.objects.filter(pk=invitation.pk).update(expires_at=timezone.now() - timedelta(days=1))
        with patch.object(OrganizationTeamInvitation, "save", side_effect=IntegrityError("write failed")):
            with self.assertRaises(IntegrityError):
                self.create()
        self.assert_pending(invitation)
        self.assertEqual(OrganizationTeamInvitation.objects.count(), 1)

    def test_removed_former_owner_can_be_reinvited_after_ownership_transfer(self):
        OrganizationMembership.objects.filter(pk=self.owner_membership.pk).update(status="REMOVED")
        self.membership(role="OWNER")
        invitation, token = self.create(inviter=self.recipient, recipient=self.owner, role="MANAGER")
        self.accept(invitation, token, recipient=self.owner)
        self.owner_membership.refresh_from_db()
        self.assertEqual((self.owner_membership.role, self.owner_membership.status), ("MANAGER", "ACTIVE"))
        self.assertEqual(get_organization_role(self.owner, self.organization), "MANAGER")


class OrganizationTeamInvitationConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.owner = User.objects.create(username="concurrent_invite_owner")
        self.recipient = User.objects.create(username="concurrent_invite_recipient")
        self.organization = Organization.objects.create(user=self.owner, name="Concurrent Team", country="GH")
        OrganizationMembership.objects.create(organization=self.organization, user=self.owner, role="OWNER")

    def race(self, *operations):
        barrier = Barrier(len(operations))

        def run(operation):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                # SQLite cannot queue row locks. Retry the entire transaction,
                # never an individual write, after its safe lock failure.
                for attempt in range(20):
                    try:
                        return operation()
                    except ValidationError:
                        return None
                    except OperationalError as error:
                        if connection.vendor != "sqlite" or "locked" not in str(error).lower() or attempt == 19:
                            raise
                        sleep(0.01 * (attempt + 1))
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=len(operations)) as pool:
            futures = [pool.submit(run, operation) for operation in operations]
            return [future.result(timeout=20) for future in futures]

    def create(self):
        return create_team_invitation(organization=self.organization, inviter=self.owner, recipient=self.recipient)

    def test_concurrent_creation_leaves_only_one_pending_invitation(self):
        results = self.race(self.create, self.create)
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(OrganizationTeamInvitation.objects.filter(status="PENDING").count(), 1)

    def test_concurrent_acceptance_consumes_token_and_creates_membership_once(self):
        invitation, token = self.create()

        def accept():
            return accept_team_invitation(invitation=invitation, recipient=self.recipient, token=token)

        results = self.race(accept, accept)
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(OrganizationMembership.objects.filter(organization=self.organization, user=self.recipient).count(), 1)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "ACCEPTED")

    def test_accept_and_revoke_cannot_both_succeed(self):
        invitation, token = self.create()
        results = self.race(
            lambda: accept_team_invitation(invitation=invitation, recipient=self.recipient, token=token),
            lambda: revoke_team_invitation(invitation=invitation, actor=self.owner),
        )
        self.assertEqual(sum(result is not None for result in results), 1)
        invitation.refresh_from_db()
        self.assertIn(invitation.status, ("ACCEPTED", "REVOKED"))
        self.assertEqual(
            OrganizationMembership.objects.filter(organization=self.organization, user=self.recipient).exists(),
            invitation.status == "ACCEPTED",
        )

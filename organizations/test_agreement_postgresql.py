from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event as ThreadEvent
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from accounts.models import User
from talents.models import TalentProfile
from .models import Organization, OrganizationTalent, OrganizationTalentEvent, TalentAgreement as Agreement, TalentAgreementConsent as Consent
from . import agreement_services as services


@skipUnless(connection.vendor == "postgresql", "Agreement row locking and migration preservation require PostgreSQL")
class AgreementPostgresTests(TransactionTestCase):
    def setUp(self):
        self.owner = User.objects.create(username="agreement_pg_owner")
        self.destination_owner = User.objects.create(username="agreement_pg_destination")
        self.user = User.objects.create(username="agreement_pg_talent")
        self.talent = TalentProfile.objects.create(user=self.user)
        self.origin = Organization.objects.create(user=self.owner, name="PG origin", country="GH")
        self.destination = Organization.objects.create(user=self.destination_owner, name="PG destination", country="GH")
        self.entry = OrganizationTalent.objects.create(organization=self.origin, talent=self.talent, name="PG player", tag="Player", status="CONFIRMED")

    def pending(self, kind="TRANSFER"):
        values = {"kind": kind, "roster_entry_id": self.entry.pk, "title": "Concurrent agreement", "terms": "Exact agreed terms"}
        if kind == "TRANSFER":
            values.update(destination_id=self.destination.pk, destination_tag="Player", destination_roster="First team")
        agreement = services.create(self.owner, values)
        services.transition(agreement.pk, self.owner, "SUBMIT", "ORIGIN", 1, True)
        if kind == "TRANSFER":
            services.transition(agreement.pk, self.destination_owner, "ACCEPT", "DESTINATION", 1, True)
        return agreement

    def race(self, first, second):
        barrier = Barrier(2)
        def run(operation):
            close_old_connections()
            try:
                barrier.wait(timeout=15); operation(); return "ok"
            except services.Conflict:
                return "conflict"
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run, op) for op in [first, second]]
            return [future.result(timeout=30) for future in futures]

    def test_duplicate_final_transfer_consent_moves_roster_once(self):
        row = self.pending()
        def accept():
            services.transition(row.pk, self.user, "ACCEPT", "TALENT", 1, True)
        self.assertEqual(sorted(self.race(accept, accept)), ["conflict", "ok"])
        row.refresh_from_db(); self.assertEqual(row.status, "COMPLETED")
        self.assertEqual(OrganizationTalent.objects.filter(organization=self.destination).count(), 1)
        self.assertEqual(Consent.objects.filter(agreement=row).count(), 3)
        self.assertEqual(OrganizationTalentEvent.objects.count(), 2)

    def test_roster_removal_racing_final_consent_never_resurrects_the_source(self):
        from . import roster_services
        from rest_framework.exceptions import ValidationError
        row = self.pending()
        def remove():
            try:
                roster_services.transition(self.entry.pk, self.owner, "REMOVE")
            except ValidationError as exc:
                raise services.Conflict() from exc
        results = self.race(
            remove,
            lambda: services.transition(row.pk, self.user, "ACCEPT", "TALENT", 1, True))
        self.assertEqual(sorted(results), ["conflict", "ok"])
        row.refresh_from_db(); self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, "REMOVED")
        completed = row.status == "COMPLETED"
        self.assertEqual(OrganizationTalent.objects.filter(organization=self.destination).count(), int(completed))
        self.assertEqual(Consent.objects.filter(agreement=row).count(), 3 if completed else 2)

    def test_withdrawal_racing_final_consent_has_one_atomic_winner(self):
        row = self.pending()
        results = self.race(
            lambda: services.transition(row.pk, self.owner, "WITHDRAW", "ORIGIN", 1, reason="Withdraw offer"),
            lambda: services.transition(row.pk, self.user, "ACCEPT", "TALENT", 1, True))
        self.assertEqual(sorted(results), ["conflict", "ok"])
        row.refresh_from_db(); self.entry.refresh_from_db()
        completed = row.status == "COMPLETED"
        self.assertIn(row.status, ["WITHDRAWN", "COMPLETED"])
        self.assertEqual(self.entry.status, "REMOVED" if completed else "CONFIRMED")
        self.assertEqual(OrganizationTalent.objects.filter(organization=self.destination).count(), int(completed))
        self.assertEqual(Consent.objects.filter(agreement=row).count(), 3 if completed else 2)

    def test_membership_revocation_and_final_consent_share_the_organization_lock(self):
        from .models import OrganizationMembership
        from .services import suspend_team_member
        OrganizationMembership.objects.create(organization=self.origin, user=self.owner, role="OWNER")
        manager = User.objects.create(username="agreement_pg_manager")
        membership = OrganizationMembership.objects.create(organization=self.origin, user=manager, role="MANAGER")
        row = services.create(self.owner, {"kind": "CONTRACT", "roster_entry_id": self.entry.pk,
            "title": "Revocable authority", "terms": "Terms"})
        services.transition(row.pk, manager, "SUBMIT", "ORIGIN", 1, True)
        results = self.race(
            lambda: suspend_team_member(organization=self.origin, actor=self.owner, membership=membership),
            lambda: services.transition(row.pk, self.user, "ACCEPT", "TALENT", 1, True))
        # If activation wins the lock, its authority was valid at activation.
        # If revocation wins, the pending signature cannot authorize activation.
        self.assertEqual(results[0], "ok")
        row.refresh_from_db(); membership.refresh_from_db()
        self.assertEqual(membership.status, "SUSPENDED")
        self.assertEqual(row.status, "ACTIVE" if results[1] == "ok" else "PENDING")
        self.assertEqual(Consent.objects.filter(agreement=row).count(), 2 if results[1] == "ok" else 1)

    def assert_safety_change_waits_for_activation(self, change):
        row = self.pending()
        checked, release, started, finished = [ThreadEvent() for _ in range(4)]
        original = services.activate
        def pause_after_activation(*args):
            original(*args)
            checked.set()
            if not release.wait(timeout=15):
                raise RuntimeError("Activation test release timed out")
        def accept():
            close_old_connections()
            try:
                services.transition(row.pk, self.user, "ACCEPT", "TALENT", 1, True)
            finally:
                close_old_connections()
        def change_safety():
            close_old_connections(); started.set()
            try:
                change(); finished.set()
            finally:
                close_old_connections()
        with patch("organizations.agreement_services.activate", side_effect=pause_after_activation):
            with ThreadPoolExecutor(max_workers=2) as pool:
                decision = pool.submit(accept)
                try:
                    self.assertTrue(checked.wait(timeout=15))
                    safety = pool.submit(change_safety)
                    self.assertTrue(started.wait(timeout=15))
                    self.assertFalse(finished.wait(timeout=0.5), "Safety change committed inside the checked decision")
                finally:
                    release.set()
                decision.result(timeout=15); safety.result(timeout=15)
        row.refresh_from_db()
        self.assertEqual(row.status, "COMPLETED")
        self.assertTrue(finished.is_set())

    def test_account_suspension_cannot_commit_between_authority_check_and_transfer_commit(self):
        self.assert_safety_change_waits_for_activation(
            lambda: User.objects.filter(pk=self.owner.pk).update(is_active=False))
        self.owner.refresh_from_db(); self.assertFalse(self.owner.is_active)

    def test_new_block_cannot_commit_between_safety_check_and_transfer_commit(self):
        from accounts.models import UserBlock
        self.assert_safety_change_waits_for_activation(
            lambda: UserBlock.objects.create(user=self.user, blocked_user=self.destination_owner))
        self.assertTrue(UserBlock.objects.filter(user=self.user, blocked_user=self.destination_owner).exists())

    def test_busy_participant_account_returns_retryable_conflict_without_partial_consent(self):
        row = self.pending()
        held, release = ThreadEvent(), ThreadEvent()
        def hold_account():
            close_old_connections()
            try:
                with transaction.atomic():
                    User.objects.select_for_update().get(pk=self.user.pk)
                    held.set()
                    if not release.wait(timeout=15):
                        raise RuntimeError("Account lock test release timed out")
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=1) as pool:
            holder = pool.submit(hold_account)
            try:
                self.assertTrue(held.wait(timeout=15))
                with self.assertRaises(services.Conflict):
                    services.transition(row.pk, self.user, "ACCEPT", "TALENT", 1, True)
            finally:
                release.set()
            holder.result(timeout=15)
        row.refresh_from_db(); self.entry.refresh_from_db()
        self.assertEqual((row.status, self.entry.status), ("PENDING", "CONFIRMED"))
        self.assertEqual(row.consents.count(), 2)
        self.assertFalse(OrganizationTalent.objects.filter(organization=self.destination).exists())
        services.transition(row.pk, self.user, "ACCEPT", "TALENT", 1, True)
        row.refresh_from_db(); self.assertEqual(row.status, "COMPLETED")

    def test_revision_racing_final_consent_never_activates_stale_terms(self):
        row = self.pending()
        results = self.race(lambda: services.revise(row.pk, self.owner, 1, {"terms": "New terms"}),
                            lambda: services.transition(row.pk, self.user, "ACCEPT", "TALENT", 1, True))
        self.assertEqual(sorted(results), ["conflict", "ok"])
        row.refresh_from_db(); self.entry.refresh_from_db()
        if row.status == "COMPLETED":
            self.assertEqual(row.revision, 1); self.assertEqual(self.entry.status, "REMOVED")
        else:
            self.assertEqual((row.status, row.revision, self.entry.status), ("DRAFT", 2, "CONFIRMED"))
            self.assertFalse(OrganizationTalent.objects.filter(organization=self.destination).exists())

    def test_duplicate_ending_acceptance_records_one_final_decision(self):
        row = self.pending("CONTRACT")
        services.transition(row.pk, self.user, "ACCEPT", "TALENT", 1, True)
        services.transition(row.pk, self.user, "REQUEST_END", "TALENT", 1, True, "Completed", expected_end_round=0)
        def end():
            services.transition(row.pk, self.owner, "ACCEPT_END", "ORIGIN", 1, True, expected_end_round=1)
        self.assertEqual(sorted(self.race(end, end)), ["conflict", "ok"])
        row.refresh_from_db(); self.assertEqual(row.status, "ENDED")
        self.assertEqual(Consent.objects.filter(agreement=row, purpose="END").count(), 2)

    def test_0013_preserves_existing_roster_and_history_without_inventing_agreements(self):
        OrganizationTalentEvent.objects.create(affiliation=self.entry, actor=self.owner, action="CONFIRM", reason="Original roster history")
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(latest))
        models = [Organization, OrganizationTalent, OrganizationTalentEvent, TalentProfile, User]
        before = [list(model.objects.order_by("pk").values()) for model in models]
        executor.migrate([("organizations", "0012_talent_rosters")])
        self.assertEqual([list(model.objects.order_by("pk").values()) for model in models], before)
        MigrationExecutor(connection).migrate(latest)
        self.assertEqual([list(model.objects.order_by("pk").values()) for model in models], before)
        self.assertFalse(Agreement.objects.exists())
        self.assertFalse(Consent.objects.exists())

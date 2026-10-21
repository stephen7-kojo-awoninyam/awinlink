from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient

from accounts.models import User, UserBlock
from talents.models import TalentProfile
from .models import Organization, OrganizationMembership, OrganizationTalent, TalentAgreement as Agreement, TalentAgreementConsent as Consent
from . import agreement_services as services


@override_settings(ALLOWED_HOSTS=["testserver"], STORAGES={
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class AgreementTests(APITestCase):
    def test_consent_requires_a_literal_boolean_without_writing_evidence(self):
        row = self.create()
        for value in ["yes", "true", "1", 1, 0, [], {}, None]:
            with self.subTest(value=value):
                response = self.act(row, self.owner, "SUBMIT", "ORIGIN", consent=value)
                self.assertEqual(response.status_code, 400, response.data)
                self.assertFalse(Consent.objects.filter(agreement_id=row["id"]).exists())
        self.assertEqual(self.submit(row)["status"], "PENDING")

    def test_create_cannot_probe_private_roster_identifiers(self):
        self.client.force_authenticate(self.outsider)
        for entry_id in [self.entry.pk, 9223372036854775807]:
            response = self.client.post(self.url("agreements"), {
                "kind": "TRANSFER", "roster_entry_id": entry_id,
                "destination_id": self.origin.pk, "destination_tag": "Player",
                "title": "Probe", "terms": "Probe"}, format="json")
            self.assertEqual(response.status_code, 404, response.data)
        self.assertFalse(Agreement.objects.exists())

    def test_changed_stored_terms_cannot_reuse_the_old_consent_digest(self):
        row = self.submit(self.create("TRANSFER"))
        self.act(row, self.destination_owner, "ACCEPT", "DESTINATION")
        # Simulate an accidental write outside the revision service. Existing
        # approvals must never authorize the new destination tag or terms.
        Agreement.objects.filter(pk=row["id"]).update(destination_tag="Changed tag", terms="Changed terms")
        response = self.act(row, self.talent_user, "ACCEPT", "TALENT")
        self.assertEqual(response.status_code, 409, response.data)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, "CONFIRMED")
        self.assertFalse(OrganizationTalent.objects.filter(organization=self.destination).exists())
        self.assertEqual(Consent.objects.filter(agreement_id=row["id"]).count(), 2)

    def test_transfer_write_failures_roll_back_every_ledger_and_roster_write(self):
        row = self.submit(self.create("TRANSFER"))
        self.act(row, self.destination_owner, "ACCEPT", "DESTINATION")
        agreement = Agreement.objects.get(pk=row["id"])
        from .models import OrganizationTalentEvent
        models = [Agreement, Consent, OrganizationTalent, OrganizationTalentEvent, services.Event]
        before = [list(model.objects.order_by("pk").values()) for model in models]
        for target in ["organizations.agreement_services.roster_event",
                       "organizations.agreement_services.Agreement.save",
                       "organizations.agreement_services.event"]:
            with self.subTest(target=target), patch(target, side_effect=RuntimeError("Injected write failure")):
                with self.assertRaises(RuntimeError):
                    self.act(row, self.talent_user, "ACCEPT", "TALENT")
            self.assertEqual([list(model.objects.order_by("pk").values()) for model in models], before)
        self.assertEqual(agreement.status, "PENDING")

    def test_private_agreements_reject_cross_role_reads_and_writes_without_side_effects(self):
        row = self.submit(self.create("TRANSFER"))
        history_url = self.url("agreement_history", pk=row["id"])
        for actor in [self.recruiter, self.viewer, self.outsider]:
            self.client.force_authenticate(actor)
            self.assertEqual(self.client.get(self.detail(row)).status_code, 404)
            self.assertEqual(self.client.get(history_url).status_code, 404)
            self.assertEqual(self.client.get(self.url("agreements"), {"entry": self.entry.pk}).data["count"], 0)
            self.assertEqual(self.client.patch(self.detail(row), {
                "expected_revision": 1, "terms": "Unauthorized terms"}, format="json").status_code, 404)
            self.assertEqual(self.act(row, actor, "ACCEPT", "TALENT").status_code, 404)
        for actor in [self.owner, self.destination_owner, self.talent_user]:
            self.client.force_authenticate(actor)
            for url in [self.detail(row), history_url, self.url("agreements")]:
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Cache-Control"], "private, no-store")
        agreement = Agreement.objects.get(pk=row["id"])
        self.assertEqual((agreement.revision, agreement.status, agreement.terms), (1, "PENDING", row["terms"]))
        self.assertEqual(agreement.consents.count(), 1)
        self.client.force_authenticate(None)
        for url in [self.detail(row), history_url]:
            self.assertEqual(self.client.get(url).status_code, 401)

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="agreement_owner")
        cls.manager = User.objects.create_user(username="agreement_manager")
        cls.destination_owner = User.objects.create_user(username="agreement_destination")
        cls.talent_user = User.objects.create_user(username="agreement_talent")
        cls.recruiter = User.objects.create_user(username="agreement_recruiter")
        cls.viewer = User.objects.create_user(username="agreement_viewer")
        cls.outsider = User.objects.create_user(username="agreement_admin", is_superuser=True, is_staff=True)
        cls.talent = TalentProfile.objects.create(user=cls.talent_user, profile_visibility="PUBLIC")
        cls.origin = Organization.objects.create(user=cls.owner, name="Origin academy", country="GH")
        cls.destination = Organization.objects.create(user=cls.destination_owner, name="Destination academy", country="GH")
        for user, role in [(cls.owner, "OWNER"), (cls.manager, "MANAGER"), (cls.recruiter, "RECRUITER"), (cls.viewer, "VIEWER")]:
            OrganizationMembership.objects.create(user=user, organization=cls.origin, role=role)
        OrganizationMembership.objects.create(user=cls.destination_owner, organization=cls.destination, role="OWNER")
        cls.entry = OrganizationTalent.objects.create(organization=cls.origin, talent=cls.talent, name="Original player", tag="Player", roster="Academy", status="CONFIRMED")

    def url(self, name, **kwargs):
        return reverse("api:organization_team:" + name, kwargs=kwargs)

    def detail(self, row):
        return self.url("agreement", pk=row["id"])

    def create(self, kind="CONTRACT", **changes):
        self.client.force_authenticate(self.owner)
        body = {"kind": kind, "roster_entry_id": self.entry.pk, "title": f"{kind} agreement", "terms": "Exact terms ✓ <script>text only</script>", "amount": "100.00", "currency": "GHS"}
        if kind == "TRANSFER":
            body.update(destination_id=self.destination.pk, destination_tag="Player", destination_roster="First team")
        response = self.client.post(self.url("agreements"), {**body, **changes}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def act(self, row, actor, action, party, **changes):
        self.client.force_authenticate(actor)
        return self.client.post(self.detail(row), {"action": action, "party": party,
            "expected_revision": row["revision"], "expected_end_round": row["end_round"], "consent": True,
            "reason": "Recorded reason", **changes}, format="json")

    def submit(self, row):
        response = self.act(row, self.owner, "SUBMIT", "ORIGIN")
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def activate(self, row):
        row = self.submit(row)
        if row["kind"] == "TRANSFER":
            response = self.act(row, self.destination_owner, "ACCEPT", "DESTINATION")
            self.assertEqual(response.status_code, 200, response.data)
        response = self.act(row, self.talent_user, "ACCEPT", "TALENT")
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_commercial_kinds_require_matching_two_party_consent_and_mutual_ending(self):
        for kind in ["SPONSORSHIP", "AMBASSADOR", "CONTRACT"]:
            row = self.create(kind)
            self.assertEqual(row["status"], "DRAFT")
            self.assertFalse(row["consents"])
            row = self.activate(row)
            self.assertEqual(row["status"], "ACTIVE")
            self.assertEqual({c["party"] for c in row["consents"]}, {"ORIGIN", "TALENT"})
            self.assertEqual({c["terms_hash"] for c in row["consents"]}, {row["terms_hash"]})
            ending = self.act(row, self.talent_user, "REQUEST_END", "TALENT").data
            self.assertEqual(ending["status"], "ENDING")
            ended = self.act(ending, self.owner, "ACCEPT_END", "ORIGIN")
            self.assertEqual(ended.status_code, 200, ended.data)
            self.assertEqual(ended.data["status"], "ENDED")
            self.assertIsNotNone(ended.data["ended_at"])
            self.assertEqual(self.act(ended.data, self.owner, "ACCEPT_END", "ORIGIN").status_code, 409)
        self.entry.refresh_from_db(); self.assertEqual(self.entry.status, "CONFIRMED")

    def test_transfer_moves_only_named_affiliation_after_all_three_parties_approve(self):
        commercial = self.activate(self.create("SPONSORSHIP"))
        other = OrganizationTalent.objects.create(organization=self.origin, talent=self.talent, name="Same talent", tag="Alumni", status="CONFIRMED")
        row = self.submit(self.create("TRANSFER"))
        accepted = self.act(row, self.destination_owner, "ACCEPT", "DESTINATION")
        self.assertEqual(accepted.status_code, 200)
        self.entry.refresh_from_db(); self.assertEqual(self.entry.status, "CONFIRMED")
        completed = self.act(row, self.talent_user, "ACCEPT", "TALENT")
        self.assertEqual(completed.status_code, 200, completed.data)
        self.assertEqual(completed.data["status"], "COMPLETED")
        self.entry.refresh_from_db(); self.assertEqual(self.entry.status, "REMOVED")
        target = OrganizationTalent.objects.get(pk=completed.data["destination_entry_id"])
        self.assertEqual((target.organization_id, target.talent_id, target.status, target.roster), (self.destination.pk, self.talent.pk, "CONFIRMED", "First team"))
        other.refresh_from_db(); self.assertEqual(other.status, "CONFIRMED")
        self.assertEqual(self.entry.history.get().action, "TRANSFERRED_OUT")
        self.assertEqual(target.history.get().action, "TRANSFERRED_IN")
        unchanged = Agreement.objects.get(pk=commercial["id"])
        self.assertEqual((unchanged.status, unchanged.organization_id, unchanged.roster_entry_id), ("ACTIVE", self.origin.pk, self.entry.pk))
        self.assertEqual(self.act(completed.data, self.owner, "REQUEST_END", "ORIGIN").status_code, 409)

    def test_drafts_and_terms_are_private_even_from_recruiters_viewers_and_admins(self):
        row = self.create("TRANSFER")
        for actor in [self.talent_user, self.destination_owner, self.viewer, self.recruiter, self.outsider]:
            self.client.force_authenticate(actor)
            self.assertEqual(self.client.get(self.detail(row)).status_code, 404)
            self.assertEqual(self.client.get(self.url("agreements")).data["count"], 0)
        row = self.submit(row)
        for actor in [self.talent_user, self.destination_owner, self.manager]:
            self.client.force_authenticate(actor)
            self.assertEqual(self.client.get(self.detail(row)).status_code, 200)
        for actor in [self.viewer, self.recruiter, self.outsider]:
            self.client.force_authenticate(actor)
            self.assertEqual(self.client.get(self.detail(row)).status_code, 404)
            self.assertEqual(self.client.get(self.url("agreement_history", pk=row["id"])).status_code, 404)
            self.assertEqual(self.client.get(self.url("agreement_roster_choices")).data["count"], 0)

    def test_consent_is_explicit_and_roles_cannot_be_forged(self):
        row = self.create()
        self.assertEqual(self.act(row, self.owner, "SUBMIT", "ORIGIN", consent=False).status_code, 400)
        self.assertFalse(Consent.objects.exists())
        row = self.submit(row)
        self.assertEqual(self.act(row, self.owner, "ACCEPT", "TALENT").status_code, 403)
        self.assertEqual(self.act(row, self.talent_user, "ACCEPT", "DESTINATION").status_code, 403)
        self.assertEqual(self.act(row, self.talent_user, "ACCEPT", "TALENT", consent=False).status_code, 400)
        self.assertEqual(Agreement.objects.get(pk=row["id"]).status, "PENDING")

    def test_revision_invalidates_old_consent_and_rejects_stale_actions(self):
        row = self.submit(self.create("TRANSFER"))
        self.act(row, self.destination_owner, "ACCEPT", "DESTINATION")
        self.client.force_authenticate(self.manager)
        response = self.client.patch(self.detail(row), {"expected_revision": 1, "terms": "New exact terms", "talent_id": self.outsider.pk}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        revised = response.data
        self.assertEqual((revised["revision"], revised["status"]), (2, "DRAFT"))
        self.assertNotEqual(revised["terms_hash"], row["terms_hash"])
        self.assertEqual(Agreement.objects.get(pk=row["id"]).talent_id, self.talent.pk)
        revised = self.submit(revised)
        self.assertEqual(self.act(row, self.talent_user, "ACCEPT", "TALENT").status_code, 409)
        accepted = self.act(revised, self.talent_user, "ACCEPT", "TALENT")
        self.assertEqual(accepted.data["status"], "PENDING", "Old destination consent must not count")
        completed = self.act(revised, self.destination_owner, "ACCEPT", "DESTINATION")
        self.assertEqual(completed.data["status"], "COMPLETED")
        self.assertEqual(Consent.objects.filter(agreement_id=row["id"], revision=1).count(), 2)

    def test_live_terms_cannot_be_edited_or_agreements_deleted(self):
        row = self.activate(self.create())
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.patch(self.detail(row), {"expected_revision": 1, "terms": "Changed after consent"}, format="json").status_code, 409)
        self.assertEqual(self.client.delete(self.detail(row)).status_code, 405)
        self.assertEqual(self.client.post(self.url("agreement_history", pk=row["id"]), {}).status_code, 405)

    def test_decline_and_withdraw_preserve_roster_and_history(self):
        row = self.submit(self.create("TRANSFER"))
        self.assertEqual(self.act(row, self.talent_user, "DECLINE", "TALENT", reason="").status_code, 400)
        declined = self.act(row, self.talent_user, "DECLINE", "TALENT", reason="Different plans")
        self.assertEqual(declined.data["status"], "DECLINED")
        self.assertEqual(self.act(row, self.destination_owner, "ACCEPT", "DESTINATION").status_code, 409)
        draft = self.create()
        withdrawn = self.act(draft, self.owner, "WITHDRAW", "ORIGIN")
        self.assertEqual(withdrawn.data["status"], "WITHDRAWN")
        self.entry.refresh_from_db(); self.assertEqual(self.entry.status, "CONFIRMED")
        self.client.force_authenticate(self.talent_user)
        history = self.client.get(self.url("agreement_history", pk=row["id"]))
        self.assertEqual(history.data["results"][-1]["reason"], "Different plans")
        self.assertEqual(history.data["results"][-1]["actor_name"], self.talent_user.username)

    def test_removed_or_unclaimed_source_cannot_be_used(self):
        row = self.submit(self.create())
        OrganizationTalent.objects.filter(pk=self.entry.pk).update(status="REMOVED")
        self.assertEqual(self.act(row, self.talent_user, "ACCEPT", "TALENT").status_code, 409)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.post(self.url("agreements"), {"roster_entry_id": self.entry.pk, "kind": "CONTRACT", "title": "X", "terms": "Terms"}, format="json").status_code, 409)
        self.assertEqual(Consent.objects.filter(agreement_id=row["id"]).count(), 1)

    def test_revoked_previous_approver_cannot_leave_usable_pending_authority(self):
        row = self.submit(self.create())
        OrganizationMembership.objects.filter(organization=self.origin, user=self.owner).update(status="SUSPENDED")
        self.assertEqual(self.act(row, self.talent_user, "ACCEPT", "TALENT").status_code, 409)
        self.assertEqual(Consent.objects.filter(agreement_id=row["id"]).count(), 1)
        self.assertEqual(self.act(row, self.owner, "WITHDRAW", "ORIGIN").status_code, 404)

    def test_destination_conflict_rolls_back_final_consent_and_both_roster_changes(self):
        row = self.submit(self.create("TRANSFER"))
        self.act(row, self.destination_owner, "ACCEPT", "DESTINATION")
        OrganizationTalent.objects.create(organization=self.destination, talent=self.talent, name="Already there", tag="Player", roster="First team", status="CONFIRMED")
        self.assertEqual(self.act(row, self.talent_user, "ACCEPT", "TALENT").status_code, 409)
        self.entry.refresh_from_db(); self.assertEqual(self.entry.status, "CONFIRMED")
        self.assertEqual(Consent.objects.filter(agreement_id=row["id"]).count(), 2)
        self.assertFalse(self.entry.history.exists())

    def test_second_pending_transfer_is_rejected_without_partial_consent(self):
        self.submit(self.create("TRANSFER"))
        second = self.create("TRANSFER")
        self.assertEqual(self.act(second, self.owner, "SUBMIT", "ORIGIN").status_code, 409)
        self.assertFalse(Consent.objects.filter(agreement_id=second["id"]).exists())
        self.assertEqual(Agreement.objects.get(pk=second["id"]).status, "DRAFT")

    def test_blocked_or_inactive_participants_cannot_activate(self):
        row = self.submit(self.create("TRANSFER"))
        block = UserBlock.objects.create(user=self.talent_user, blocked_user=self.destination_owner)
        self.assertEqual(self.act(row, self.destination_owner, "ACCEPT", "DESTINATION").status_code, 403)
        block.delete()
        Organization.objects.filter(pk=self.destination.pk).update(status="INACTIVE")
        self.assertEqual(self.act(row, self.talent_user, "ACCEPT", "TALENT").status_code, 409)
        self.assertEqual(Consent.objects.filter(agreement_id=row["id"]).count(), 1)

    def test_ending_rounds_reject_stale_consent_and_self_decline(self):
        row = self.activate(self.create())
        first = self.act(row, self.talent_user, "REQUEST_END", "TALENT").data
        self.assertEqual(self.act(first, self.talent_user, "DECLINE_END", "TALENT").status_code, 409)
        active = self.act(first, self.owner, "DECLINE_END", "ORIGIN").data
        self.assertEqual(active["status"], "ACTIVE")
        second = self.act(active, self.talent_user, "REQUEST_END", "TALENT").data
        self.assertEqual(second["end_round"], 2)
        self.assertEqual(self.act(first, self.owner, "ACCEPT_END", "ORIGIN").status_code, 409)
        self.assertEqual(self.act(second, self.owner, "ACCEPT_END", "ORIGIN").data["status"], "ENDED")

    def test_event_failure_rolls_back_transfer_and_consent(self):
        row = self.submit(self.create("TRANSFER"))
        self.act(row, self.destination_owner, "ACCEPT", "DESTINATION")
        original = services.event
        def fail(agreement, actor, action, *args, **kwargs):
            if action == "TRANSFER_COMPLETED":
                raise RuntimeError("Synthetic event write failure")
            return original(agreement, actor, action, *args, **kwargs)
        with patch("organizations.agreement_services.event", side_effect=fail):
            with self.assertRaises(RuntimeError):
                self.act(row, self.talent_user, "ACCEPT", "TALENT")
        self.entry.refresh_from_db(); self.assertEqual(self.entry.status, "CONFIRMED")
        self.assertFalse(OrganizationTalent.objects.filter(organization=self.destination).exists())
        self.assertEqual(Consent.objects.filter(agreement_id=row["id"]).count(), 2)

    def test_validation_and_unauthenticated_endpoints(self):
        self.client.force_authenticate(self.owner)
        base = {"roster_entry_id": self.entry.pk, "kind": "CONTRACT", "title": "Contract", "terms": "Terms"}
        for invalid in [{"amount": "NaN"}, {"amount": "-1"}, {"currency": "GH"}, {"terms": ""},
                        {"starts_on": "2026-12-02", "ends_on": "2026-12-01"}, {"destination_id": self.destination.pk},
                        {"kind": "TRANSFER", "destination_id": self.origin.pk, "destination_tag": "Player"}]:
            self.assertEqual(self.client.post(self.url("agreements"), {**base, **invalid}, format="json").status_code, 400)
        self.client.force_authenticate(None)
        for name in ["agreements", "agreement_roster_choices", "agreement_destinations"]:
            self.assertEqual(self.client.get(self.url(name)).status_code, 401)

    def test_session_csrf_and_web_shell(self):
        client = APIClient(enforce_csrf_checks=True); client.force_login(self.owner)
        self.assertEqual(client.post(self.url("agreements"), {"kind": "CONTRACT"}, format="json").status_code, 403)
        page = client.get(reverse("organization_agreements"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'name="csrfmiddlewaretoken"')

    def test_withdrawing_a_never_submitted_draft_does_not_publish_its_terms(self):
        row = self.create("TRANSFER")
        self.assertEqual(self.act(row, self.owner, "WITHDRAW", "ORIGIN").status_code, 200)
        for actor in [self.talent_user, self.destination_owner]:
            self.client.force_authenticate(actor)
            self.assertEqual(self.client.get(self.detail(row)).status_code, 404)
            self.assertEqual(self.client.get(self.url("agreements")).data["count"], 0)
        # A previously submitted revision must not publish a later private draft.
        row = self.submit(self.create("TRANSFER"))
        self.client.force_authenticate(self.owner)
        revised = self.client.patch(self.detail(row), {"expected_revision": 1, "terms": "Private revised draft"}, format="json").data
        self.assertEqual(self.act(revised, self.owner, "WITHDRAW", "ORIGIN").status_code, 200)
        self.client.force_authenticate(self.talent_user)
        prior = self.client.get(self.detail(row))
        self.assertEqual(prior.status_code, 200)
        self.assertEqual((prior.data["status"], prior.data["revision"], prior.data["terms"]), ("SUPERSEDED", 1, row["terms"]))
        self.assertFalse(prior.data["actions"])
        history = self.client.get(self.url("agreement_history", pk=row["id"]))
        self.assertTrue(history.data["results"])
        self.assertTrue(all(e["revision"] == 1 for e in history.data["results"]))
        self.assertNotIn("Private revised draft", str(history.data))

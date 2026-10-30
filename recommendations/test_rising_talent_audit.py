"""Scale, restart, retention and concurrency regressions for the batch job."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from zoneinfo import ZoneInfo
from io import StringIO
from threading import Barrier, Event
from unittest import skipUnless
from unittest.mock import patch

from django.core.management import call_command, CommandError
from django.db import close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django.urls import reverse

from accounts.models import User, UserBlock
from coaches.models import CoachProfile
from scouts.models import ScoutProfile
from organizations.models import Organization, OrganizationMembership
from notifications.models import Notification
from skills.models import Skill, SkillCategory
from talents.models import TalentProfile, Achievement
from . import rising_talent as service
from .models import RisingTalentPreference as Preference, RisingTalentSnapshot as Snapshot, RisingTalentAlert as Alert
from .rising_job import plan_alerts, recipient_batches, run_alerts


class AuditFixtures:
    def make_talent(self, name):
        user = User.objects.create_user(username=name, role="ATHLETE")
        talent = TalentProfile.objects.create(user=user, talent_category="SCIENCE_TECHNOLOGY")
        talent.skills.set(self.skills)
        Preference.objects.create(user=user, discovery_enabled=True)
        Achievement.objects.bulk_create([Achievement(talent=talent, title=f"Award {i}", date_received=self.day) for i in range(3)])
        return talent

    def make_recipient(self, name, role="SCOUT"):
        user = User.objects.create_user(username=name, role=role)
        if role == "SCOUT":
            ScoutProfile.objects.create(user=user, scout_category="SCIENCE_TECHNOLOGY")
        elif role == "COACH":
            CoachProfile.objects.create(user=user, coach_category="SCIENCE_TECHNOLOGY")
        preference = Preference.objects.create(user=user, category="SCIENCE_TECHNOLOGY", alerts_enabled=True)
        preference.skills.add(self.skills[0])
        return user

    def make_fixture(self):
        self.day = timezone.localdate()
        category = SkillCategory.objects.create(name="Audit skills")
        self.skills = [Skill.objects.create(category=category, name=name) for name in ["Robotics", "Design", "Programming", "Research"]]
        self.talent = self.make_talent("audit-first-talent")
        self.recipient = self.make_recipient("audit-scout")


class RisingJobAuditTests(AuditFixtures, TestCase):
    def setUp(self):
        self.make_fixture()

    def preferences(self):
        return list(Preference.objects.filter(alerts_enabled=True).select_related("user", "organization").prefetch_related("skills"))

    def test_alert_creation_and_delivery_never_recompute_the_full_ranking(self):
        with patch.object(service, "matches_for", side_effect=AssertionError("Unexpected whole-ranking scan")):
            self.assertTrue(service.notify_match(self.recipient, self.talent.pk))
            self.assertTrue(service.notification_is_current(Notification.objects.get(user=self.recipient)))

    def test_sent_top_five_do_not_starve_other_talents_on_a_later_day(self):
        talents = [self.talent] + [self.make_talent(f"starvation-{i}") for i in range(8)]
        first = run_alerts()
        self.assertEqual(first["alerts"], 5)
        Alert.objects.update(created_at=timezone.now() - timedelta(days=1))
        second = run_alerts()
        self.assertEqual(second["alerts"], 4)
        self.assertEqual(set(Alert.objects.values_list("talent_id", flat=True)), {talent.pk for talent in talents})

    def test_retry_after_partial_failure_completes_without_duplicate_alerts(self):
        for i in range(5):
            self.make_talent(f"restart-{i}")
        calls = 0
        real_notify = service.notify_match
        def fail_third(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise RuntimeError("Synthetic interruption")
            return real_notify(*args, **kwargs)
        with patch("recommendations.rising_job.notify_match", side_effect=fail_third):
            with self.assertRaises(RuntimeError):
                run_alerts()
        self.assertEqual(Alert.objects.count(), 2)
        self.assertEqual(run_alerts()["alerts"], 3)
        self.assertEqual(Alert.objects.count(), 5)
        self.assertEqual(Notification.objects.count(), 5)

    def test_scoring_is_shared_across_recipients_and_does_not_scale_per_candidate_queries(self):
        for i in range(9):
            self.make_recipient(f"shared-recipient-{i}")
        preferences = self.preferences()
        with CaptureQueriesContext(connection) as one:
            plan_alerts(preferences, self.day)
        for i in range(39):
            self.make_talent(f"shared-candidate-{i}")
        with patch.object(service, "assess", wraps=service.assess) as assess:
            with CaptureQueriesContext(connection) as many:
                planned = plan_alerts(preferences, self.day)
        self.assertEqual(assess.call_count, 40)  # 40, not 40 candidates x 10 recipients.
        self.assertEqual(len(planned), 10)
        self.assertLessEqual(len(many), len(one) + 2)
        self.assertTrue(all(len(ids) <= 5 for _, ids in planned))

    def test_snapshots_are_bulk_created_and_second_run_skips_existing_observations(self):
        with CaptureQueriesContext(connection) as one:
            self.assertEqual(service.record_snapshots(), 1)
        for i in range(39):
            self.make_talent(f"snapshot-scale-{i}")
        with CaptureQueriesContext(connection) as many:
            self.assertEqual(service.record_snapshots(), 39)
        self.assertLessEqual(len(many), len(one) + 2)
        with patch.object(service, "safe_skills", side_effect=AssertionError("Already observed")):
            self.assertEqual(service.record_snapshots(), 0)

    def test_single_candidate_checks_do_not_scan_the_skill_catalog(self):
        with patch.object(service, "normalize_topic", wraps=service.normalize_topic) as normalize:
            self.assertIsNotNone(service.match_for_talent(self.recipient, self.talent.pk))
            before = normalize.call_count
        Skill.objects.bulk_create([Skill(category=self.skills[0].category, name=f"Unrelated catalog {i}") for i in range(1000)])
        with patch.object(service, "normalize_topic", wraps=service.normalize_topic) as normalize:
            self.assertIsNotNone(service.match_for_talent(self.recipient, self.talent.pk))
            self.assertEqual(normalize.call_count, before)

    def test_block_checks_read_only_edges_relevant_to_the_candidate_page(self):
        unrelated = User.objects.bulk_create([User(username=f"unrelated-block-{i}") for i in range(200)])
        UserBlock.objects.bulk_create([UserBlock(user=self.recipient, blocked_user=user) for user in unrelated])
        self.assertEqual(service.blocked_pairs({self.recipient.pk}, {self.talent.user_id}), set())
        self.assertEqual(len(service.matches_for(self.recipient)), 1)
        UserBlock.objects.create(user=self.talent.user, blocked_user=self.recipient)
        with patch.object(service, "assess", side_effect=AssertionError("Blocked evidence must not be scored")):
            self.assertEqual(service.matches_for(self.recipient), [])
            self.assertIsNone(service.match_for_talent(self.recipient, self.talent.pk))

    def test_daily_cap_skips_candidate_scoring_and_uses_timestamp_range(self):
        for i in range(5):
            Alert.objects.create(recipient=self.recipient, talent=None, period=self.day - timedelta(days=i * 7))
        with patch.object(service, "assess", side_effect=AssertionError("Daily quota exhausted")):
            self.assertEqual(plan_alerts(self.preferences(), self.day), [])
            self.assertFalse(service.notify_match(self.recipient, self.talent.pk))
        with CaptureQueriesContext(connection) as queries:
            service.notify_match(self.recipient, self.talent.pk)
        receipt_sql = [row["sql"].lower() for row in queries if "risingtalentalert" in row["sql"].lower()]
        self.assertTrue(receipt_sql)
        self.assertFalse(any("datetime_cast_date" in sql or "::date" in sql for sql in receipt_sql))

    def test_recipient_keyset_resume_does_not_skip_or_repeat_a_partial_group(self):
        for i in range(6):
            self.make_recipient(f"cursor-{i}")
        first = run_alerts(dry_run=True, batch_size=3, max_recipients=4)
        second = run_alerts(dry_run=True, batch_size=3, after=first["recipient_after"])
        self.assertEqual((first["processed"], second["processed"]), (4, 3))
        self.assertEqual(first["matches"] + second["matches"], 7)
        self.assertFalse(Alert.objects.exists())
        self.assertFalse(Snapshot.objects.exists())

    def test_invalid_job_bounds_fail_before_any_write(self):
        for options in ({"batch_size": 0}, {"batch_size": 101}, {"recipient_after": -1}, {"max_recipients": 0}):
            with self.assertRaises(CommandError):
                call_command("detect_rising_talent", stdout=StringIO(), **options)
        self.assertFalse(Snapshot.objects.exists())

    def test_selected_organization_authority_is_rechecked_for_coaches_and_scouts(self):
        owner = User.objects.create_user(username="selected-owner", role="ORGANIZATION")
        org = Organization.objects.create(user=owner, name="Selected scope", country="GH")
        for i, role in enumerate(("COACH", "SCOUT")):
            user = self.make_recipient(f"scoped-{i}", role=role)
            member = OrganizationMembership.objects.create(organization=org, user=user, role="VIEWER")
            Preference.objects.filter(user=user).update(organization=org)
            self.assertEqual(len(service.matches_for(user)), 1)
            member.status = "REMOVED"; member.save()
            self.assertEqual(service.matches_for(user), [])
            self.assertFalse(service.notify_match(user, self.talent.pk))

    def test_organization_owner_and_blocks_are_fresh_even_with_cached_preferences(self):
        first = User.objects.create_user(username="old-scope-owner", role="ORGANIZATION")
        second = User.objects.create_user(username="new-scope-owner", role="ORGANIZATION")
        org = Organization.objects.create(user=first, name="Owner changes", country="GH")
        OrganizationMembership.objects.create(organization=org, user=self.recipient, role="VIEWER")
        Preference.objects.filter(user=self.recipient).update(organization=org)
        cached = service.preference_for(self.recipient)
        Organization.objects.filter(pk=org.pk).update(user=second)
        UserBlock.objects.create(user=second, blocked_user=self.talent.user)
        self.assertEqual(service.matches_for(self.recipient, preference=cached), [])

    def test_privacy_and_skills_are_rechecked_after_job_planning(self):
        planned = plan_alerts(self.preferences(), self.day)
        self.assertEqual(len(planned), 1)
        self.talent.skills.clear()
        self.assertFalse(service.notify_match(planned[0][0], planned[0][1][0]))
        self.assertFalse(Alert.objects.exists())

    def test_secret_rotation_does_not_bypass_an_erased_weekly_receipt(self):
        with override_settings(SECRET_KEY="old-audit-secret", SECRET_KEY_FALLBACKS=[]):
            self.assertTrue(service.notify_match(self.recipient, self.talent.pk))
            service.set_preferences(self.talent.user, {"discovery_enabled": False})
            service.set_preferences(self.talent.user, {"discovery_enabled": True})
        with override_settings(SECRET_KEY="new-audit-secret", SECRET_KEY_FALLBACKS=["old-audit-secret"]):
            self.assertFalse(service.notify_match(self.recipient, self.talent.pk))
            self.assertEqual(plan_alerts(self.preferences(), self.day), [])
        self.assertEqual(Alert.objects.count(), 1)

    def test_large_evidence_is_bounded_and_fails_closed_instead_of_inflating_scores(self):
        Achievement.objects.bulk_create([Achievement(talent=self.talent, title=f"Excess {i}", date_received=self.day)
                                        for i in range(service.MAX_ACHIEVEMENTS)])
        loaded = service.evidence_rows(TalentProfile.objects.filter(pk=self.talent.pk), self.day).get()
        self.assertEqual(len(loaded.rising_achievements), service.MAX_ACHIEVEMENTS + 1)
        result = service.assess(loaded)
        self.assertFalse(result["qualified"])
        self.assertFalse(result["evidence_complete"])
        self.assertEqual(service.matches_for(self.recipient), [])
        self.assertFalse(service.notify_match(self.recipient, self.talent.pk))

        self.client.force_login(self.talent.user)
        page = self.client.get(reverse("rising_talent"))
        self.assertContains(page, "Automatic matching paused. No score was assigned.")
        self.assertNotContains(page, "0/100")

    def test_only_the_earliest_usable_baseline_is_loaded(self):
        Snapshot.objects.bulk_create([Snapshot(talent=self.talent, day=self.day - timedelta(days=i), skill_topics=[])
                                     for i in range(7, 91)])
        loaded = service.evidence_rows(TalentProfile.objects.filter(pk=self.talent.pk), self.day).get()
        self.assertEqual(len(loaded.rising_baselines), 1)
        self.assertEqual(loaded.rising_baselines[0].day, self.day - timedelta(days=90))

    def test_excess_public_skills_are_bounded_and_not_recorded_as_a_baseline(self):
        extra = Skill.objects.bulk_create([Skill(category=self.skills[0].category, name=f"Skill {i}")
                                          for i in range(service.MAX_PUBLIC_SKILLS)])
        self.talent.skills.add(*extra)
        loaded = service.evidence_rows(TalentProfile.objects.filter(pk=self.talent.pk), self.day).get()
        self.assertEqual(len(loaded.rising_skills), service.MAX_PUBLIC_SKILLS + 1)
        self.assertFalse(service.assess(loaded)["evidence_complete"])
        self.assertEqual(service.record_snapshots(), 0)

    def test_daily_bounds_cover_daylight_saving_transitions(self):
        with timezone.override(ZoneInfo("America/Los_Angeles")):
            start, end = service.day_bounds(date(2026, 11, 1))
            hours = (end.astimezone(ZoneInfo("UTC")) - start.astimezone(ZoneInfo("UTC"))).total_seconds() / 3600
            self.assertEqual(hours, 25)
            start, end = service.day_bounds(date(2026, 3, 8))
            hours = (end.astimezone(ZoneInfo("UTC")) - start.astimezone(ZoneInfo("UTC"))).total_seconds() / 3600
            self.assertEqual(hours, 23)

    def test_retention_and_withdrawal_erase_in_bounded_batches(self):
        for i in range(9):
            notification = Notification.objects.create(user=self.recipient, message="Generic", metadata={"feature": "rising_talent"})
            Alert.objects.create(recipient=self.recipient, talent=self.talent, period=self.day - timedelta(days=i * 7), notification=notification)
        batches = []
        from django.db.models.query import QuerySet
        real_qs_delete = QuerySet.delete
        def checked_delete(rows):
            if rows.model is Notification:
                batches.append(rows.count())
            return real_qs_delete(rows)
        with patch.object(QuerySet, "delete", checked_delete):
            service.erase_alert_links(Alert.objects.filter(talent=self.talent), batch_size=3)
        self.assertEqual(batches, [3, 3, 3])
        self.assertFalse(Alert.objects.filter(talent=self.talent).exists())
        self.assertEqual(Alert.objects.count(), 9)
        Alert.objects.update(created_at=timezone.now() - timedelta(days=91))
        service.record_snapshots(batch_size=3)
        self.assertFalse(Alert.objects.exists())


class RisingJobScaleTests(TestCase):
    def test_thousand_candidates_share_scoring_for_hundred_recipients(self):
        day = timezone.localdate()
        category = SkillCategory.objects.create(name="Scale catalog")
        skills = Skill.objects.bulk_create([Skill(category=category, name=name) for name in ("Robotics", "Programming", "Design")])
        users = User.objects.bulk_create([User(username=f"scale-talent-{i}", role="ATHLETE") for i in range(1000)])
        talents = TalentProfile.objects.bulk_create([TalentProfile(user=user, talent_category="SCIENCE_TECHNOLOGY") for user in users])
        Preference.objects.bulk_create([Preference(user=user, discovery_enabled=True) for user in users])
        TalentProfile.skills.through.objects.bulk_create([TalentProfile.skills.through(talentprofile_id=talent.pk, skill_id=skill.pk)
                                                          for talent in talents for skill in skills])
        Achievement.objects.bulk_create([Achievement(talent=talent, title=f"Award {i}", date_received=day,
                                                     description="Unused private text " * 100)
                                        for talent in talents for i in range(3)])
        recipients = User.objects.bulk_create([User(username=f"scale-scout-{i}", role="SCOUT") for i in range(100)])
        ScoutProfile.objects.bulk_create([ScoutProfile(user=user, scout_category="SCIENCE_TECHNOLOGY") for user in recipients])
        prefs = Preference.objects.bulk_create([Preference(user=user, category="SCIENCE_TECHNOLOGY", alerts_enabled=True) for user in recipients])
        Preference.skills.through.objects.bulk_create([Preference.skills.through(risingtalentpreference_id=pref.pk, skill_id=skills[0].pk) for pref in prefs])
        batch = next(recipient_batches())
        with patch.object(service, "assess", wraps=service.assess) as assess:
            with CaptureQueriesContext(connection) as queries:
                planned = plan_alerts(batch, day)
        self.assertEqual(assess.call_count, 1000)
        self.assertEqual(len(planned), 100)
        self.assertEqual(sum(len(ids) for _, ids in planned), 500)
        self.assertLess(len(queries), 300)
        evidence_sql = [query["sql"] for query in queries if '"talents_achievement"' in query["sql"]]
        self.assertTrue(evidence_sql)
        self.assertFalse(any('"description"' in sql or '"image"' in sql for sql in evidence_sql))
        self.assertFalse(Notification.objects.exists())


@skipUnless(connection.vendor == "postgresql", "Requires real PostgreSQL row locks")
class RisingJobPostgresTests(AuditFixtures, TransactionTestCase):
    def setUp(self):
        self.make_fixture()
        self.publish = patch("notifications.signals.publish_notification").start()
        self.addCleanup(patch.stopall)

    def race(self, operations):
        barrier = Barrier(len(operations))
        def run(operation):
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                return operation()
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=len(operations)) as pool:
            futures = [pool.submit(run, operation) for operation in operations]
            return [future.result(timeout=60) for future in futures]

    def test_overlapping_workers_create_one_receipt_and_one_notification(self):
        results = self.race([lambda: service.notify_match(self.recipient, self.talent.pk)] * 2)
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(Alert.objects.count(), 1)
        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(self.publish.call_count, 1)

    def test_concurrent_distinct_candidates_cannot_exceed_daily_cap(self):
        talents = [self.talent] + [self.make_talent(f"daily-race-{i}") for i in range(7)]
        operations = [lambda talent=talent: service.notify_match(self.recipient, talent.pk) for talent in talents]
        results = self.race(operations)
        self.assertEqual(sum(results), service.MAX_DAILY_ALERTS)
        self.assertEqual(Notification.objects.count(), service.MAX_DAILY_ALERTS)

    def test_concurrent_source_withdrawal_leaves_no_link_or_notification(self):
        self.race([lambda: service.notify_match(self.recipient, self.talent.pk),
                   lambda: service.set_preferences(self.talent.user, {"discovery_enabled": False})])
        self.assertFalse(Alert.objects.filter(talent=self.talent).exists())
        self.assertFalse(Notification.objects.exists())

    def test_concurrent_snapshot_jobs_record_one_baseline(self):
        results = self.race([lambda: service.record_snapshots()] * 2)
        self.assertEqual(sum(results), 1)
        self.assertEqual(Snapshot.objects.filter(talent=self.talent).count(), 1)

    def test_overlapping_full_jobs_preserve_caps_and_unique_baselines(self):
        for i in range(2):
            self.make_talent(f"full-job-{i}")
        self.make_recipient("full-job-coach", role="COACH")
        self.race([lambda: call_command("detect_rising_talent", stdout=StringIO())] * 2)
        self.assertEqual(Snapshot.objects.count(), 3)
        self.assertEqual(Alert.objects.count(), 6)
        self.assertEqual(Notification.objects.count(), 6)

    def test_snapshot_does_not_preserve_skills_read_before_the_consent_lock(self):
        observed = Event()
        original = service.keyset_batches
        def pause_at_candidates(rows, *args, **kwargs):
            for batch in original(rows, *args, **kwargs):
                if rows.model is TalentProfile:
                    observed.set()
                yield batch
        def worker():
            close_old_connections()
            try:
                return service.record_snapshots()
            finally:
                close_old_connections()
        with patch.object(service, "keyset_batches", side_effect=pause_at_candidates):
            with ThreadPoolExecutor(max_workers=1) as pool:
                with transaction.atomic():
                    Preference.objects.select_for_update().get(user=self.talent.user)
                    future = pool.submit(worker)
                    self.assertTrue(observed.wait(timeout=15))
                    self.talent.skills.set([self.skills[-1]])
                self.assertEqual(future.result(timeout=30), 1)
        self.assertEqual(Snapshot.objects.get(talent=self.talent).skill_topics, ["research"])

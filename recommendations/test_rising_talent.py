import json
from datetime import timedelta
from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User, UserBlock
from coaches.models import CoachProfile
from scouts.models import ScoutProfile
from organizations.models import Organization, OrganizationMembership
from notifications.models import Notification, MobilePushToken
from skills.models import Skill, SkillCategory
from talents.models import TalentProfile, Achievement
from .models import RisingTalentPreference as Preference, RisingTalentSnapshot as Snapshot, RisingTalentAlert as Alert
from .rising_talent import (assess, CATEGORIES, matches_for, notify_match, notification_is_current,
                            record_snapshots, set_preferences)


@override_settings(ALLOWED_HOSTS=["testserver"], STORAGES={
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class RisingTalentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.day = timezone.localdate()
        cls.skill_category = SkillCategory.objects.create(name="Rising skills")
        cls.skills = [Skill.objects.create(category=cls.skill_category, name=name)
                      for name in ("Robotics", "Programming", "Design", "Engineering", "Research", "Leadership")]
        cls.talent_user = User.objects.create_user(username="rising-person", role="ATHLETE")
        cls.talent = TalentProfile.objects.create(user=cls.talent_user, talent_category="SCIENCE_TECHNOLOGY")
        cls.talent.skills.set(cls.skills[:4])
        Preference.objects.create(user=cls.talent_user, discovery_enabled=True)
        for i in range(3):
            Achievement.objects.create(talent=cls.talent, title=f"Project award {i}", date_received=cls.day - timedelta(days=i))
        cls.scout = User.objects.create_user(username="rising-scout", role="SCOUT")
        cls.coach = User.objects.create_user(username="rising-coach", role="COACH")
        ScoutProfile.objects.create(user=cls.scout, scout_category="SCIENCE_TECHNOLOGY")
        CoachProfile.objects.create(user=cls.coach, coach_category="SCIENCE_TECHNOLOGY")
        cls.owner = User.objects.create_user(username="rising-org", role="ORGANIZATION")
        cls.org = Organization.objects.create(user=cls.owner, name="Rising organization", country="GH")
        cls.outsider = User.objects.create_user(username="rising-admin", role="ADMIN", is_staff=True, is_superuser=True)
        for user in (cls.scout, cls.coach, cls.owner):
            pref = Preference.objects.create(user=user, alerts_enabled=True, category="SCIENCE_TECHNOLOGY",
                                             organization=cls.org if user == cls.owner else None)
            pref.skills.add(cls.skills[0])

    def api(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_scores_explain_actual_evidence_without_inventing_a_growth_baseline(self):
        result = assess(self.talent, self.day)
        self.assertEqual(result["score"], 65)
        self.assertEqual(result["score"], sum(result["components"].values()))
        self.assertTrue(result["qualified"])
        self.assertFalse(result["baseline_available"])
        self.assertEqual(result["components"]["skill_growth"], 0)
        self.assertTrue(any("no skill growth points" in reason for reason in result["explanations"]))
        self.assertTrue(any("self-reported" in reason for reason in result["explanations"]))

    def test_measured_skill_growth_requires_seven_days_and_is_capped(self):
        Snapshot.objects.create(talent=self.talent, day=self.day - timedelta(days=6), skill_topics=[])
        self.assertEqual(assess(self.talent)["components"]["skill_growth"], 0)
        baseline = Snapshot.objects.create(talent=self.talent, day=self.day - timedelta(days=7), skill_topics=["robotics"])
        self.assertEqual(assess(self.talent)["components"]["skill_growth"], 30)
        self.talent.skills.set(self.skills)
        self.assertEqual(assess(self.talent)["score"], 100)
        baseline.day = self.day - timedelta(days=91); baseline.save()
        self.assertEqual(assess(self.talent)["components"]["skill_growth"], 0)

    def test_duplicate_achievements_unknown_future_and_old_dates_do_not_inflate_scores(self):
        expected = assess(self.talent)["score"]
        Achievement.objects.create(talent=self.talent, title="  PROJECT AWARD 0  ", date_received=self.day)
        for date in (None, self.day + timedelta(days=1), self.day - timedelta(days=90)):
            Achievement.objects.create(talent=self.talent, title="New upload", date_received=date)
        self.assertEqual(assess(self.talent)["score"], expected)

    def test_skill_aliases_are_not_double_counted_or_treated_as_new_growth(self):
        ai = Skill.objects.create(category=self.skill_category, name="AI")
        canonical = Skill.objects.create(category=self.skill_category, name="Artificial intelligence")
        self.talent.skills.set([ai, canonical])
        Snapshot.objects.create(talent=self.talent, day=self.day - timedelta(days=10), skill_topics=["artificial intelligence"])
        result = assess(self.talent)
        self.assertEqual(result["components"]["skills"], 5)
        self.assertEqual(result["components"]["skill_growth"], 0)
        self.assertFalse(result["qualified"])

    def test_declining_achievement_activity_does_not_earn_growth_points(self):
        Achievement.objects.filter(talent=self.talent).update(date_received=self.day - timedelta(days=45))
        Achievement.objects.create(talent=self.talent, title="Current", date_received=self.day)
        self.assertEqual(assess(self.talent)["components"]["achievement_growth"], 0)
        self.assertFalse(assess(self.talent)["qualified"])

    def test_popularity_location_verification_and_private_portfolio_are_not_scoring_inputs(self):
        from portfolio.models import PortfolioItem
        expected = assess(self.talent)
        TalentProfile.objects.filter(pk=self.talent.pk).update(followers_count=999999, verified=True, country="Elsewhere")
        PortfolioItem.objects.create(talent=self.talent, title="Unrelated activity", item_type="PROJECT")
        self.assertEqual(assess(self.talent), expected)

    def test_all_four_categories_match_organizations_scouts_and_coaches(self):
        for category in CATEGORIES:
            TalentProfile.objects.filter(pk=self.talent.pk).update(talent_category=category)
            for recipient in (self.scout, self.coach, self.owner):
                Preference.objects.filter(user=recipient).update(category=category)
                matches = matches_for(recipient)
                self.assertEqual([row["talent_id"] for row in matches], [self.talent.pk])
                self.assertIn("Robotics", matches[0]["match_explanation"])
                self.assertEqual(matches[0]["category"], category)

    def test_category_and_skill_overlap_are_both_required(self):
        pref = Preference.objects.get(user=self.scout)
        pref.category = "ARTS"; pref.save()
        self.assertEqual(matches_for(self.scout), [])
        pref.category = "SCIENCE_TECHNOLOGY"; pref.save()
        pref.skills.set([self.skills[-1]])
        self.assertEqual(matches_for(self.scout), [])
        pref.skills.clear()
        self.assertEqual(matches_for(self.scout), [])

    def test_low_evidence_is_not_padded_into_results(self):
        Achievement.objects.filter(talent=self.talent).delete()
        self.assertFalse(assess(self.talent)["qualified"])
        self.assertEqual(matches_for(self.scout), [])

    def test_private_opted_out_inactive_and_wrong_role_candidates_are_excluded_immediately(self):
        Preference.objects.filter(user=self.talent_user).update(discovery_enabled=False)
        self.assertEqual(matches_for(self.scout), [])
        Preference.objects.filter(user=self.talent_user).update(discovery_enabled=True)
        for visibility in ("PRIVATE", "ORGANIZATIONS"):
            TalentProfile.objects.filter(pk=self.talent.pk).update(profile_visibility=visibility)
            self.assertEqual(matches_for(self.scout), [])
        TalentProfile.objects.filter(pk=self.talent.pk).update(profile_visibility="PUBLIC")
        User.objects.filter(pk=self.talent_user.pk).update(is_active=False)
        self.assertEqual(matches_for(self.scout), [])
        User.objects.filter(pk=self.talent_user.pk).update(is_active=True, role="ADMIN")
        self.assertEqual(matches_for(self.scout), [])

    def test_blocks_in_both_directions_and_organization_owner_blocks_are_enforced(self):
        for a, b in ((self.scout, self.talent_user), (self.talent_user, self.scout),
                     (self.owner, self.talent_user), (self.talent_user, self.owner)):
            block = UserBlock.objects.create(user=a, blocked_user=b)
            recipient = self.scout if self.scout in (a, b) else self.owner
            self.assertEqual(matches_for(recipient), [])
            self.assertFalse(notify_match(recipient, self.talent.pk))
            block.delete()

    def test_organization_permissions_are_rechecked_without_admin_bypass(self):
        self.assertEqual(len(matches_for(self.owner)), 1)
        membership = OrganizationMembership.objects.create(organization=self.org, user=self.owner, role="VIEWER", status="SUSPENDED")
        self.assertEqual(matches_for(self.owner), [])
        membership.status = "ACTIVE"; membership.save()
        self.assertEqual(len(matches_for(self.owner)), 1)
        Organization.objects.filter(pk=self.org.pk).update(status="INACTIVE")
        self.assertEqual(matches_for(self.owner), [])
        pref = Preference.objects.create(user=self.outsider, category="SCIENCE_TECHNOLOGY", organization=self.org, alerts_enabled=True)
        pref.skills.add(self.skills[0])
        self.assertEqual(matches_for(self.outsider), [])

    def test_daily_snapshots_are_idempotent_and_expire(self):
        Snapshot.objects.create(talent=self.talent, day=self.day - timedelta(days=91), skill_topics=["old"])
        self.assertEqual(record_snapshots(), 1)
        self.assertEqual(record_snapshots(), 0)
        self.assertEqual(Snapshot.objects.filter(talent=self.talent).count(), 1)
        self.assertEqual(Snapshot.objects.get(talent=self.talent).skill_topics, ["robotics", "programming", "design", "engineering"])

    def test_notifications_are_weekly_deduplicated_generic_and_post_commit(self):
        with patch("notifications.signals.publish_notification") as publish:
            with self.captureOnCommitCallbacks(execute=True):
                self.assertTrue(notify_match(self.scout, self.talent.pk))
                self.assertFalse(notify_match(self.scout, self.talent.pk))
                publish.assert_not_called()
            publish.assert_called_once()
        notification = Notification.objects.get(user=self.scout)
        self.assertNotIn(self.talent_user.username, notification.message)
        self.assertNotIn("Robotics", notification.message)
        self.assertEqual(notification.metadata, {"feature": "rising_talent"})
        self.assertTrue(notification_is_current(notification))
        self.assertEqual(Alert.objects.count(), 1)
        self.assertTrue(notify_match(self.scout, self.talent.pk, day=self.day + timedelta(days=7)))

    def test_alert_creation_and_delivery_recheck_consent_relevance_and_permissions(self):
        self.assertTrue(notify_match(self.scout, self.talent.pk))
        notification = Notification.objects.get(user=self.scout)
        Preference.objects.filter(user=self.scout).update(alerts_enabled=False)
        self.assertFalse(notification_is_current(notification))
        self.assertFalse(notify_match(self.scout, self.talent.pk))
        Preference.objects.filter(user=self.scout).update(alerts_enabled=True, category="ARTS")
        self.assertFalse(notification_is_current(notification))
        Preference.objects.filter(user=self.scout).update(category="SCIENCE_TECHNOLOGY")
        User.objects.filter(pk=self.scout.pk).update(is_active=False)
        self.assertFalse(notification_is_current(notification))

    def test_optout_purges_derived_data_and_notifications(self):
        record_snapshots()
        notify_match(self.scout, self.talent.pk)
        set_preferences(self.talent_user, {"discovery_enabled": False})
        self.assertFalse(Snapshot.objects.filter(talent=self.talent).exists())
        self.assertFalse(Alert.objects.filter(talent=self.talent).exists())
        self.assertFalse(Notification.objects.filter(user=self.scout).exists())
        self.assertEqual(matches_for(self.scout), [])

    def test_private_profile_save_withdraws_discovery_and_does_not_reenable_on_public(self):
        record_snapshots(); notify_match(self.scout, self.talent.pk)
        self.talent.profile_visibility = "PRIVATE"; self.talent.save()
        self.assertFalse(Preference.objects.get(user=self.talent_user).discovery_enabled)
        self.assertFalse(Snapshot.objects.exists())
        self.assertFalse(Alert.objects.filter(talent=self.talent).exists())
        self.talent.profile_visibility = "PUBLIC"; self.talent.save()
        self.assertEqual(matches_for(self.scout), [])

    def test_withdrawal_erases_match_links_without_resetting_recipient_alert_limits(self):
        self.assertTrue(notify_match(self.scout, self.talent.pk))
        set_preferences(self.talent_user, {"discovery_enabled": False})
        receipt = Alert.objects.get(recipient=self.scout)
        self.assertIsNone(receipt.talent_id)
        self.assertIsNone(receipt.notification_id)
        self.assertEqual(len(receipt.deduplication_key), 64)
        set_preferences(self.talent_user, {"discovery_enabled": True})
        self.assertFalse(notify_match(self.scout, self.talent.pk))
        self.assertFalse(Notification.objects.filter(user=self.scout).exists())

    def test_recipient_alert_optout_erases_match_links_and_preserves_rate_limits(self):
        self.assertTrue(notify_match(self.scout, self.talent.pk))
        set_preferences(self.scout, {"alerts_enabled": False})
        self.assertFalse(Notification.objects.filter(user=self.scout).exists())
        self.assertIsNone(Alert.objects.get(recipient=self.scout).talent_id)
        set_preferences(self.scout, {"alerts_enabled": True})
        self.assertFalse(notify_match(self.scout, self.talent.pk))

    def test_batch_dry_run_has_no_writes_and_real_run_is_repeatable(self):
        output = StringIO()
        before = Notification.objects.count()
        call_command("detect_rising_talent", dry_run=True, stdout=output)
        self.assertIn("3 matches", output.getvalue())
        self.assertEqual(Notification.objects.count(), before)
        self.assertFalse(Snapshot.objects.exists())
        call_command("detect_rising_talent", stdout=StringIO())
        call_command("detect_rising_talent", stdout=StringIO())
        self.assertEqual(Alert.objects.count(), 3)
        self.assertEqual(Snapshot.objects.count(), 1)

    def test_preferences_are_opt_in_private_and_only_editable_by_their_owner(self):
        client = self.api(self.outsider)
        count = Preference.objects.count()
        response = client.get(reverse("api:rising_talent_preferences"))
        self.assertFalse(response.data["discovery_enabled"])
        self.assertFalse(response.data["alerts_enabled"])
        self.assertEqual(Preference.objects.count(), count)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertEqual(client.patch(reverse("api:rising_talent_preferences"), {"discovery_enabled": True, "user": self.talent_user.pk}, format="json").status_code, 400)
        self.assertTrue(Preference.objects.get(user=self.talent_user).discovery_enabled)
        self.assertEqual(client.get(reverse("api:rising_talent_matches")).data, {"results": [], "assessment": None})

    def test_preference_validation_requires_public_talent_and_authorized_recipient(self):
        url = reverse("api:rising_talent_preferences")
        client = self.api(self.talent_user)
        TalentProfile.objects.filter(pk=self.talent.pk).update(profile_visibility="PRIVATE")
        self.assertEqual(client.patch(url, {"discovery_enabled": True}, format="json").status_code, 400)
        self.assertEqual(client.patch(url, {"discovery_enabled": False}, format="json").status_code, 200)
        self.assertEqual(self.api(self.outsider).patch(url, {"alerts_enabled": True, "category": "SCIENCE_TECHNOLOGY", "skills": [self.skills[0].pk], "organization": self.org.pk}, format="json").status_code, 400)
        self.assertEqual(self.api(self.scout).patch(url, {"category": "invalid"}, format="json").status_code, 400)
        self.assertEqual(self.api(self.scout).patch(url, {"skills": []}, format="json").status_code, 400)

    def test_alert_optout_is_allowed_after_permissions_are_revoked(self):
        OrganizationMembership.objects.create(organization=self.org, user=self.owner, role="VIEWER", status="REMOVED")
        client = self.api(self.owner)
        response = client.patch(reverse("api:rising_talent_preferences"), {"alerts_enabled": False}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data["alerts_enabled"])

    def test_web_withdrawal_bypasses_expired_organization_and_skill_validation(self):
        OrganizationMembership.objects.create(organization=self.org, user=self.owner, role="VIEWER", status="REMOVED")
        self.client.force_login(self.owner)
        response = self.client.post(reverse("rising_talent"), {"action": "withdraw", "organization": 999999})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Preference.objects.get(user=self.owner).alerts_enabled)

    def test_matching_is_ranked_and_ties_are_stable(self):
        second_user = User.objects.create_user(username="rising-ranked", role="ATHLETE")
        second = TalentProfile.objects.create(user=second_user, talent_category="SCIENCE_TECHNOLOGY")
        second.skills.set(self.skills)
        Preference.objects.create(user=second_user, discovery_enabled=True)
        for i in range(3):
            Achievement.objects.create(talent=second, title=f"Award {i}", date_received=self.day)
        self.assertEqual([row["talent_id"] for row in matches_for(self.scout)], [second.pk, self.talent.pk])
        second.skills.set(self.skills[:4])
        self.assertEqual([row["talent_id"] for row in matches_for(self.scout)], [self.talent.pk, second.pk])

    def test_delivery_does_not_broadcast_a_match_after_a_block(self):
        from notifications.signals import publish_notification
        notify_match(self.scout, self.talent.pk)
        notification = Notification.objects.get(user=self.scout)
        UserBlock.objects.create(user=self.talent_user, blocked_user=self.scout)
        with patch("notifications.push.send_push_notification") as web, patch("notifications.push.send_expo_rising_talent_push") as native:
            publish_notification(notification.pk)
            web.assert_not_called()
            native.assert_not_called()

    def test_sensitive_skills_are_excluded_from_detection_options_and_matching_preferences(self):
        sensitive = Skill.objects.create(category=self.skill_category, name="Political affiliation")
        before = assess(self.talent)["score"]
        self.talent.skills.add(sensitive)
        self.assertEqual(assess(self.talent)["score"], before)
        client = self.api(self.scout)
        self.assertEqual(client.patch(reverse("api:rising_talent_preferences"), {"skills": [sensitive.pk]}, format="json").status_code, 400)
        options = client.get(reverse("api:rising_talent_options")).data
        self.assertNotIn(sensitive.pk, [row["id"] for row in options["skills"]])

    def test_matches_api_exposes_explanations_but_not_raw_history_or_contact_details(self):
        response = self.api(self.scout).get(reverse("api:rising_talent_matches"))
        self.assertEqual(response.status_code, 200)
        result = response.data["results"][0]
        self.assertIn("match_explanation", result)
        self.assertIn("explanations", result["assessment"])
        serialized = json.dumps(response.data)
        for private in ("email", "skill_topics", "Project award", "date_received", "biography"):
            self.assertNotIn(private, serialized)
        self.assertIsNone(response.data["assessment"])
        own = self.api(self.talent_user).get(reverse("api:rising_talent_matches"))
        self.assertEqual(own.data["assessment"]["score"], 65)

    def test_web_csrf_preferences_and_escaped_explanations(self):
        self.talent_user.first_name = "<script>bad</script>"; self.talent_user.save()
        self.client.force_login(self.scout)
        page = self.client.get(reverse("rising_talent"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "&lt;script&gt;bad&lt;/script&gt;")
        self.assertContains(page, "Why this talent?")
        self.assertContains(page, 'name="csrfmiddlewaretoken"')
        client = APIClient(enforce_csrf_checks=True); client.force_login(self.scout)
        self.assertEqual(client.patch(reverse("api:rising_talent_preferences"), {"alerts_enabled": False}, format="json").status_code, 403)

    def test_web_preferences_save_an_explicit_focus_and_skills(self):
        self.client.force_login(self.scout)
        response = self.client.post(reverse("rising_talent"), {
            "alerts_enabled": "on", "category": "ARTS", "skills": [self.skills[2].pk], "organization": "",
        })
        self.assertEqual(response.status_code, 302)
        pref = Preference.objects.get(user=self.scout)
        self.assertEqual(pref.category, "ARTS")
        self.assertTrue(pref.alerts_enabled)
        self.assertEqual(list(pref.skills.values_list("pk", flat=True)), [self.skills[2].pk])

    def test_api_authentication_and_own_assessment_cannot_be_overridden(self):
        client = APIClient()
        for name in ("rising_talent_preferences", "rising_talent_matches", "rising_talent_options"):
            self.assertEqual(client.get(reverse("api:" + name)).status_code, 401)
        response = self.api(self.outsider).get(reverse("api:rising_talent_matches"), {"talent_id": self.talent.pk})
        self.assertIsNone(response.data["assessment"])

    def test_daily_alert_cap_is_enforced(self):
        from .rising_talent import MAX_DAILY_ALERTS
        for i in range(MAX_DAILY_ALERTS):
            Alert.objects.create(recipient=self.scout, talent=self.talent, period=self.day - timedelta(days=i * 7))
        self.assertFalse(notify_match(self.scout, self.talent.pk))
        self.assertFalse(Notification.objects.filter(user=self.scout).exists())

    def test_database_prevents_duplicate_snapshots_and_alerts(self):
        Snapshot.objects.create(talent=self.talent, day=self.day)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Snapshot.objects.create(talent=self.talent, day=self.day)
        Alert.objects.create(recipient=self.scout, talent=self.talent, period=self.day)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Alert.objects.create(recipient=self.scout, talent=self.talent, period=self.day)

    def test_push_payload_is_generic_and_suppresses_stale_matches(self):
        from notifications.push import notification_payload, send_expo_rising_talent_push
        notify_match(self.scout, self.talent.pk)
        notification = Notification.objects.get(user=self.scout)
        MobilePushToken.objects.create(user=self.scout, token="ExponentPushToken[rising-fixture]", platform="android")
        response = Mock(); response.__enter__ = Mock(return_value=response); response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"data": [{"status": "ok"}]}'
        with patch("notifications.push.urlopen", return_value=response) as send:
            send_expo_rising_talent_push(notification)
            payload = json.loads(send.call_args.args[0].data)[0]
            self.assertEqual(payload["data"], {"type": "rising_talent", "notification_id": notification.pk})
            self.assertNotIn(self.talent_user.username, json.dumps(payload))
        self.assertEqual(notification_payload(notification)["data"]["type"], "rising_talent")
        Preference.objects.filter(user=self.talent_user).update(discovery_enabled=False)
        with patch("notifications.push.urlopen") as send:
            send_expo_rising_talent_push(notification)
            send.assert_not_called()


class RisingTalentMigrationTests(TransactionTestCase):
    def restore_schema(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_forward_migration_preserves_profiles_and_existing_consent_without_opting_anyone_in(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        self.addCleanup(self.restore_schema)
        executor = MigrationExecutor(connection)
        before = [("recommendations", "0002_recommendationinterestpreference_and_more")]
        executor.migrate(before)
        targets = [node for node in executor.loader.graph.leaf_nodes() if node[0] != "recommendations"] + before
        state = executor.loader.project_state(targets).apps
        user = state.get_model("accounts", "User").objects.create(username="rising-migration")
        profile = state.get_model("talents", "TalentProfile").objects.create(user_id=user.pk, talent_category="ARTS")
        consent = state.get_model("recommendations", "RecommendationInterestPreference").objects.create(user_id=user.pk, inferred_interests_enabled=True)
        saved_profile = state.get_model("talents", "TalentProfile").objects.values().get(pk=profile.pk)
        saved_consent = state.get_model("recommendations", "RecommendationInterestPreference").objects.values().get(pk=consent.pk)
        self.restore_schema()
        from .models import RecommendationInterestPreference
        self.assertEqual(TalentProfile.objects.values().get(pk=profile.pk), saved_profile)
        self.assertEqual(RecommendationInterestPreference.objects.values().get(pk=consent.pk), saved_consent)
        self.assertFalse(Preference.objects.exists())
        self.assertFalse(Snapshot.objects.exists())
        self.assertFalse(Alert.objects.exists())

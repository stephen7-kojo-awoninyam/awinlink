from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from recommendations.management.commands.seed_recommendation_users import evaluate
from talents.models import TalentProfile


@override_settings(DEBUG=True)
class RecommendationSeedTests(TestCase):
    def seed(self, **kwargs):
        call_command("seed_recommendation_users", stdout=StringIO(), **kwargs)

    def test_exact_count_diversity_and_repeatability(self):
        self.seed()
        original = list(get_user_model().objects.values_list("pk", flat=True))
        self.seed()
        self.assertEqual(list(get_user_model().objects.values_list("pk", flat=True)), original)
        self.assertEqual(len(original), 90)
        self.assertEqual(TalentProfile.objects.count(), 90)
        self.assertEqual(TalentProfile.objects.values("talent_area").distinct().count(), 9)
        for user in get_user_model().objects.all():
            self.assertFalse(user.has_usable_password())
            self.assertTrue(user.email.endswith("@example.invalid"))
            self.assertEqual(user.talent_profile.skills.count(), 1)
            self.assertEqual(user.talent_profile.domains.count(), 1)

    @override_settings(DEBUG=False)
    def test_production_rejected_before_writes(self):
        with self.assertRaises(CommandError):
            self.seed()
        self.assertEqual(get_user_model().objects.count(), 0)

    def test_hosted_environment_rejected(self):
        with patch.dict("os.environ", {"RENDER": "true"}):
            with self.assertRaises(CommandError):
                self.seed()
        self.assertEqual(get_user_model().objects.count(), 0)

    def test_application_database_rejected(self):
        from django.db import connection
        with patch.dict(connection.settings_dict, {"NAME": "db.sqlite3"}):
            with self.assertRaises(CommandError):
                self.seed()

    def test_conflict_rolls_back_entire_seed(self):
        get_user_model().objects.create_user(username="fictional_rec_020", email="real@example.invalid")
        with self.assertRaises(CommandError):
            self.seed()
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertEqual(TalentProfile.objects.count(), 0)

    def test_both_engines_return_relevant_non_self_results(self):
        self.seed()
        users = list(get_user_model().objects.order_by("username"))
        for pipeline in ("legacy", "unified"):
            report = evaluate(users, pipeline)
            self.assertEqual(report["users"], 90)
            self.assertEqual(report["user_coverage_percent"], 100)
            self.assertEqual(report["slot_relevance_at_5_percent"], 100)
            self.assertEqual(report["recall_at_5_percent"], 55.56)

    def test_empty_results_are_counted_as_missing_slots(self):
        self.seed()
        users = list(get_user_model().objects.order_by("username"))
        with patch("recommendations.services.RecommendationEngine.recommend_talents_for_talent", return_value=[]):
            report = evaluate(users, "legacy")
        self.assertEqual(report["precision_at_5_percent"], 0)
        self.assertEqual(report["slot_relevance_at_5_percent"], 0)
        self.assertEqual(report["user_coverage_percent"], 0)

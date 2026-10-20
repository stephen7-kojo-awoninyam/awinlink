from io import StringIO
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from applications.models import Application
from learning.models import Course, Enrollment
from opportunities.models import Opportunity
from organizations.models import Organization
from recommendations.local_benchmark import (
    CandidateLabel, FixtureManifest, benchmark_surface, recommendations_for,
    seed_extended_fixtures, summarize_results,
)
from recommendations.management.commands.seed_recommendation_users import GROUPS, PREFIX
from talents.models import TalentProfile


class BenchmarkMetricTests(SimpleTestCase):
    def test_duplicates_unknowns_ineligible_and_unrelated_results_do_not_inflate_precision(self):
        catalog = {
            1: CandidateLabel(0), 2: CandidateLabel(0, eligible=False),
            3: CandidateLabel(1), 4: CandidateLabel(0, excluded_users={7}),
        }
        report = summarize_results([(7, [1, 1, 2, 3, 4, 999], 10)], catalog, {7: 0})
        self.assertEqual(report["relevant_results"], 1)
        self.assertEqual(report["precision_at_5_percent"], 16.67)
        self.assertEqual(report["topic_precision_at_5_percent"], 50)
        self.assertEqual(report["eligible_result_percent"], 33.33)
        self.assertEqual(report["slot_relevance_at_5_percent"], 20)
        self.assertEqual(report["recall_at_5_percent"], 100)

    def test_abstention_has_zero_coverage_and_undefined_precision(self):
        report = summarize_results([(7, [], 2)], {1: CandidateLabel(0)}, {7: 0})
        self.assertIsNone(report["precision_at_5_percent"])
        self.assertEqual(report["slot_relevance_at_5_percent"], 0)
        self.assertEqual(report["user_coverage_percent"], 0)
        self.assertEqual(report["recall_at_5_percent"], 0)

    @override_settings(UNIFIED_RECOMMENDATIONS_ENABLED=False,
                       RECOMMENDATION_INTEREST_LEARNING_ENABLED=True)
    def test_pipeline_flags_are_controlled_and_restored(self):
        from types import SimpleNamespace
        manifest = FixtureManifest(segments={"profiled": [SimpleNamespace(pk=7)]}, user_cohorts={7: 0})
        observed = []

        def capture(*args):
            observed.append((settings.UNIFIED_RECOMMENDATIONS_ENABLED,
                             settings.RECOMMENDATION_INTEREST_LEARNING_ENABLED))
            return []

        with patch("recommendations.local_benchmark.recommendations_for", side_effect=capture):
            for pipeline in ("legacy", "unified"):
                report = benchmark_surface(manifest, pipeline, "organizations", "profiled")
                self.assertEqual(report["backend"], "shared_legacy_no_unified_adapter")
        self.assertEqual(observed, [(False, False), (True, False)])
        self.assertFalse(settings.UNIFIED_RECOMMENDATIONS_ENABLED)
        self.assertTrue(settings.RECOMMENDATION_INTEREST_LEARNING_ENABLED)


@override_settings(DEBUG=True)
class ExtendedRecommendationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_recommendation_users", extended=True, stdout=StringIO())
        cls.users = list(get_user_model().objects.filter(
            username__in=[f"{PREFIX}{index:03d}" for index in range(1, 91)],
        ).order_by("username"))
        cls.manifest = seed_extended_fixtures(cls.users, GROUPS, PREFIX)

    def subset(self, segment, users):
        return FixtureManifest(segments={segment: users}, user_cohorts=self.manifest.user_cohorts,
                               catalogs=self.manifest.catalogs)

    def test_extended_seed_repeats_without_duplicates_and_cold_profiles_are_distinct(self):
        original = list(get_user_model().objects.order_by("username").values_list("pk", flat=True))
        call_command("seed_recommendation_users", extended=True, stdout=StringIO())
        self.assertEqual(list(get_user_model().objects.order_by("username").values_list("pk", flat=True)), original)
        self.assertEqual(len(original), 99)
        self.assertEqual(TalentProfile.objects.count(), 96)
        self.assertEqual(Opportunity.objects.count(), 90)
        self.assertEqual(Course.objects.count(), 90)
        self.assertEqual(Organization.objects.count(), 72)
        for segment, users in self.manifest.segments.items():
            if segment == "profiled":
                continue
            for user in users:
                self.assertFalse(user.has_usable_password())
                self.assertFalse(Course.objects.filter(creator=user).exists())
                self.assertFalse(Enrollment.objects.filter(user=user).exists())
                self.assertFalse(Application.objects.filter(talent__user=user).exists())
                profile = TalentProfile.objects.filter(user=user).first()
                if segment == "cold_no_profile":
                    self.assertIsNone(profile)
                else:
                    expected = int(segment == "cold_profile_only")
                    self.assertEqual(profile.domains.count(), expected)
                    self.assertEqual(profile.skills.count(), expected)

    def test_new_surfaces_across_every_cohort_and_both_pipelines(self):
        representatives = self.users[::10]
        manifest = self.subset("profiled", representatives)
        for pipeline in ("legacy", "unified"):
            for surface in ("opportunities", "courses", "organizations"):
                with self.subTest(pipeline=pipeline, surface=surface):
                    report = benchmark_surface(manifest, pipeline, surface, "profiled")
                    self.assertEqual(report["user_coverage_percent"], 100)
                    self.assertEqual(report["topic_precision_at_5_percent"], 100)
                    if surface == "organizations":
                        # Existing engine scores closed orgs; the benchmark must expose this.
                        self.assertEqual(report["eligible_result_percent"], 80)
                        self.assertEqual(report["precision_at_5_percent"], 80)
                    else:
                        self.assertEqual(report["eligible_result_percent"], 100)
                        self.assertEqual(report["precision_at_5_percent"], 100)

    def test_applied_owned_and_enrolled_items_are_excluded(self):
        user = self.users[0]
        applied = set(Application.objects.filter(talent__user=user).values_list("opportunity_id", flat=True))
        enrolled = set(Enrollment.objects.filter(user=user).values_list("course_id", flat=True))
        own = set(Course.objects.filter(creator=user).values_list("pk", flat=True))
        self.assertTrue(applied and enrolled and own)
        for pipeline in ("legacy", "unified"):
            opportunities = recommendations_for(user, "opportunities", pipeline)
            courses = recommendations_for(user, "courses", pipeline)
            self.assertEqual(len(opportunities), 5)
            self.assertEqual(len(courses), 5)
            self.assertFalse({item.pk for item in opportunities} & applied)
            self.assertFalse({item.pk for item in courses} & (enrolled | own))
            self.assertTrue(all(item.active and item.organization.status == "ACTIVE" for item in opportunities))
            self.assertTrue(all(item.status == "APPROVED" for item in courses))

    def test_cold_start_coverage_and_held_out_labels_for_both_pipelines(self):
        for pipeline in ("legacy", "unified"):
            for segment in ("cold_no_profile", "cold_empty_profile", "cold_profile_only"):
                for surface in ("talents", "opportunities", "courses", "organizations"):
                    with self.subTest(pipeline=pipeline, segment=segment, surface=surface):
                        report = benchmark_surface(self.manifest, pipeline, surface, segment)
                        abstains = (segment == "cold_no_profile" and surface != "organizations"
                                    or segment == "cold_empty_profile" and surface == "talents")
                        self.assertEqual(report["user_coverage_percent"], 0 if abstains else 100)
                        if abstains:
                            self.assertIsNone(report["precision_at_5_percent"])
                            self.assertEqual(report["slot_relevance_at_5_percent"], 0)
                        if segment == "cold_profile_only":
                            self.assertEqual(report["precision_at_5_percent"], 80 if surface == "organizations" else 100)
                        else:
                            self.assertEqual(report["ground_truth"], "held_out_cohort")

    def test_new_options_require_extended_mode_before_seeding(self):
        for options in ({"surfaces": ["courses"]}, {"report": "unused.json"}):
            with self.assertRaises(CommandError):
                call_command("seed_recommendation_users", stdout=StringIO(), **options)

    def test_conflicting_cold_user_rolls_back_catalog_updates(self):
        user = self.manifest.segments["cold_empty_profile"][0]
        user.email = "conflict@example.invalid"
        user.save(update_fields=["email"])
        with self.assertRaises(CommandError):
            call_command("seed_recommendation_users", extended=True, stdout=StringIO())
        self.assertEqual(get_user_model().objects.count(), 99)
        self.assertEqual(Course.objects.count(), 90)

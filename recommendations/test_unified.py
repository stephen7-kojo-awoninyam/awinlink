from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from recommendations.unified import (
    UnifiedRecommendationService,
    adaptive_recommendation_limit,
    diversify_recommendations,
    unified_recommendations_enabled,
)


class UnifiedRecommendationTests(SimpleTestCase):
    def test_cold_start_without_talent_profile_does_not_invent_profile_based_results(self):
        user = SimpleNamespace(is_authenticated=True)
        engine = Mock()
        service = UnifiedRecommendationService(engine)

        self.assertEqual(service._viewer_topics(user), set())
        self.assertEqual(service.recommend_talents(user), [])
        self.assertEqual(service.recommend_learning(user), [])
        self.assertEqual(service.recommend_events(user), [])
        self.assertEqual(service.recommend_connections(user), [])
        engine.recommend_talents_for_talent.assert_not_called()
        engine.recommend_courses_for_talent.assert_not_called()
        engine.recommend_events_for_talent.assert_not_called()
        engine.recommend_sub_ecosystems.assert_not_called()

    def test_rollout_flag_is_disabled_unless_explicitly_enabled(self):
        self.assertFalse(unified_recommendations_enabled())
        with override_settings(UNIFIED_RECOMMENDATIONS_ENABLED=True):
            self.assertTrue(unified_recommendations_enabled())

    def test_diversity_ranking_inserts_a_relevant_new_topic_and_keeps_scores(self):
        first = {"score": 90, "matched_topics": ["artificial intelligence"], "item": "first"}
        repetitive = {"score": 86, "matched_topics": ["artificial intelligence"], "item": "repeat"}
        diverse = {"score": 85, "matched_topics": ["machine learning"], "item": "diverse"}

        ranked = diversify_recommendations([first, repetitive, diverse], limit=3)

        self.assertEqual([row["item"] for row in ranked], ["first", "diverse", "repeat"])
        self.assertEqual([row["score"] for row in ranked], [90, 85, 86])

    def test_diversity_never_jumps_a_candidate_outside_the_relevance_band(self):
        results = [
            {"score": 100, "matched_topics": ["ai"], "item": "best"},
            {"score": 89, "matched_topics": ["sports"], "item": "outside-band"},
        ]
        self.assertEqual(
            [row["item"] for row in diversify_recommendations(results)],
            ["best", "outside-band"],
        )

    def test_adaptive_limit_trims_a_weak_tail_but_keeps_small_catalogs(self):
        rows = [{"score": score} for score in (100, 96, 90, 70, 60)]
        self.assertEqual(adaptive_recommendation_limit(rows, requested=5), 3)
        self.assertEqual(adaptive_recommendation_limit(rows[:2], requested=5), 2)

    def test_exact_skill_match_is_explained_and_gets_a_bounded_score_nudge(self):
        relation = SimpleNamespace(values_list=lambda *args, **kwargs: ["AI"])
        viewer = SimpleNamespace(skills=relation, domains=SimpleNamespace(values_list=lambda *a, **k: []))
        candidate = SimpleNamespace(skills=SimpleNamespace(values_list=lambda *a, **k: ["artificial intelligence"]))
        service = UnifiedRecommendationService(Mock())

        result = service._result("course", viewer, candidate, 50)

        self.assertEqual(result["matched_topics"], ["artificial intelligence"])
        self.assertEqual(result["score"], 53)
        self.assertIn("artificial intelligence", result["explanation"])

    def test_matched_topics_include_normalized_sub_ecosystem_focus(self):
        relation = SimpleNamespace(values_list=lambda *args, **kwargs: ["AI"])
        owner = SimpleNamespace(pk=17, is_authenticated=True)
        talent = SimpleNamespace(user=owner, domains=relation, skills=relation)
        candidate = SimpleNamespace(
            domains=SimpleNamespace(values_list=lambda *args, **kwargs: ["artificial intelligence"]),
            skills=SimpleNamespace(values_list=lambda *args, **kwargs: ["machine learning"]),
        )
        engine = Mock()
        engine.recommend_sub_ecosystems.return_value = [{"focus": "machine learning"}]
        service = UnifiedRecommendationService(engine)

        result = service._result("talent", talent, candidate, 61)

        self.assertEqual(result["matched_topics"], ["artificial intelligence", "machine learning"])
        self.assertIn("machine learning", result["explanation"])
        engine.recommend_sub_ecosystems.assert_called_once_with(owner)

    def test_recommendation_kinds_share_result_shape_and_keep_scores(self):
        engine = Mock()
        item_a = SimpleNamespace()
        item_b = SimpleNamespace()
        engine.recommend_opportunities_for_user.return_value = [
            {"opportunity": item_a, "score": 68.25},
            {"opportunity": item_b, "score": 51},
        ]
        service = UnifiedRecommendationService(engine)

        results = service.recommend_opportunities(SimpleNamespace(), limit=2)

        self.assertEqual([r["score"] for r in results], [68.25, 51.0])
        for result in results:
            self.assertEqual(
                set(("kind", "item", "score", "matched_topics", "explanation")),
                set(result) & {"kind", "item", "score", "matched_topics", "explanation"},
            )
            self.assertEqual(result["kind"], "opportunity")
            self.assertTrue(result["explanation"])

    def test_feed_adapter_preserves_existing_score_order_and_metadata(self):
        engine = Mock()
        engine.score_post_for_user.side_effect = lambda user, post: post.score
        older = SimpleNamespace(score=20, created_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
        newer = SimpleNamespace(score=20, created_at=datetime(2025, 2, 1, tzinfo=timezone.utc))
        high_post = SimpleNamespace(score=45, created_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
        high = SimpleNamespace(post=high_post, created_at=high_post.created_at)
        service = UnifiedRecommendationService(engine)

        results = service.rank_feed_items(
            SimpleNamespace(),
            [{"type": "post", "object": older}, {"type": "share", "object": high},
             {"type": "post", "object": newer}],
        )

        self.assertEqual([result["item"] for result in results], [high, newer, older])
        self.assertEqual([result["score"] for result in results], [45.0, 20.0, 20.0])
        self.assertEqual(results[0]["feed_type"], "share")
        self.assertEqual(engine.score_post_for_user.call_count, 3)

    def test_existing_learning_and_event_rows_are_wrapped_without_rescoring(self):
        engine = Mock()
        talent = object()
        user = SimpleNamespace(talent_profile=talent)
        course, event = object(), object()
        engine.recommend_courses_for_talent.return_value = [
            {"course": course, "score": 73, "reason": "Matches your skills."}
        ]
        engine.recommend_events_for_talent.return_value = [
            {"event": event, "score": 42, "reason": "Matches your domain."}
        ]
        service = UnifiedRecommendationService(engine)

        course_result = service.recommend_learning(user)[0]
        event_result = service.recommend_events(user)[0]

        self.assertEqual((course_result["item"], course_result["score"]), (course, 73.0))
        self.assertEqual((event_result["item"], event_result["score"]), (event, 42.0))
        self.assertEqual(course_result["explanation"], "Matches your skills.")
        self.assertEqual(event_result["explanation"], "Matches your domain.")
        engine.recommend_courses_for_talent.assert_called_once_with(talent, limit=10)
        engine.recommend_events_for_talent.assert_called_once_with(talent, limit=10)

    def test_connection_results_reuse_public_discovery_candidates_and_scores(self):
        engine = Mock()
        talent = object()
        candidate = SimpleNamespace(user_id=31, user=SimpleNamespace(is_active=True))
        engine.recommend_talents_for_talent.return_value = [
            {"talent": candidate, "score": 80, "reasons": ["Shared domain"],
             "discovery_type": "SIMILAR"}
        ]
        service = UnifiedRecommendationService(engine)

        with patch("connections.models.Connection.objects.filter") as connection_filter:
            connection_filter.return_value.values_list.return_value = []
            results = service.recommend_connections(SimpleNamespace(talent_profile=talent))

        self.assertEqual(results[0]["kind"], "connection")
        self.assertIs(results[0]["item"], candidate)
        self.assertEqual(results[0]["score"], 80.0)
        self.assertEqual(results[0]["explanation"], "Shared domain")
        engine.recommend_talents_for_talent.assert_called_once_with(talent, limit=100)
        connection_filter.assert_called_once()

    def test_connection_suggestions_exclude_pending_candidates(self):
        engine = Mock()
        talent = object()
        candidate = SimpleNamespace(user_id=31, user=SimpleNamespace(is_active=True))
        engine.recommend_talents_for_talent.return_value = [
            {"talent": candidate, "score": 80, "reasons": ["Shared domain"]}
        ]
        service = UnifiedRecommendationService(engine)
        blocked_query = Mock()
        blocked_query.values_list.side_effect = lambda *fields, **kwargs: [(None, 31)]
        blocked_query.filter.return_value = blocked_query

        with patch("connections.models.Connection.objects.filter", return_value=blocked_query) as connection_filter:
            results = service.recommend_connections(SimpleNamespace(talent_profile=talent))

        self.assertEqual(results, [])
        connection_filter.assert_called_once_with(status__in=("PENDING", "ACCEPTED"))

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from talents.models import TalentProfile


TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(
    UNIFIED_RECOMMENDATIONS_ENABLED=True,
    STORAGES=TEST_STORAGES,
    ALLOWED_HOSTS=["testserver"],
)
class UnifiedRecommendationRolloutTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="unified_rollout_viewer",
            password="TestPass123!",
            role="ATHLETE",
        )
        TalentProfile.objects.create(user=self.user, talent_category="SCIENCE_TECHNOLOGY")
        self.client.force_login(self.user)

    def test_feed_uses_unified_ranker_after_building_authorized_feed_candidates(self):
        with patch("core.views.UnifiedRecommendationService") as service:
            service.return_value.rank_feed_items.return_value = []

            response = self.client.get(reverse("home_feed"))

        self.assertEqual(response.status_code, 200)
        service.return_value.rank_feed_items.assert_called_once()
        candidate_entries = service.return_value.rank_feed_items.call_args.args[1]
        self.assertIsInstance(candidate_entries, list)

    def test_opportunities_events_learning_and_connections_use_flagged_service(self):
        cases = (
            ("opportunities.views", "recommend_opportunities", "recommended_opportunities"),
            ("events.views", "recommend_events", "recommended_events"),
            ("learning.views", "recommend_learning", "courses"),
            ("connections.views", "recommend_connections", "connections:connections_list"),
        )
        for module, method, route in cases:
            with self.subTest(surface=method):
                with patch(f"{module}.UnifiedRecommendationService") as service:
                    getattr(service.return_value, method).return_value = []

                    response = self.client.get(reverse(route))

                self.assertEqual(response.status_code, 200)
                getattr(service.return_value, method).assert_called_once()

    def test_flag_off_keeps_legacy_opportunity_fallback(self):
        with override_settings(UNIFIED_RECOMMENDATIONS_ENABLED=False):
            with patch("opportunities.views.UnifiedRecommendationService") as service:
                response = self.client.get(reverse("recommended_opportunities"))

        self.assertEqual(response.status_code, 200)
        service.assert_not_called()

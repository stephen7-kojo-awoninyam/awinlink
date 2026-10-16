from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from applications.models import Application
from connections.models import Follow
from domains.models import TalentDomain
from feed.models import Post, PostLike, SavedPost
from learning.models import Course, Enrollment, LearningCategory
from opportunities.models import Opportunity
from organizations.models import Organization
from recommendations.interest_learning import InterestLearningService
from recommendations.models import RecommendationFeedback, RecommendationInterestPreference
from recommendations.unified import UnifiedRecommendationService
from talents.models import TalentProfile


@override_settings(
    RECOMMENDATION_INTEREST_LEARNING_ENABLED=True,
    UNIFIED_RECOMMENDATIONS_ENABLED=True,
    RECOMMENDATION_INTEREST_HALF_LIFE_DAYS=60,
)
class RecommendationInterestLearningTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.viewer = User.objects.create_user(username="interest_viewer", role="ATHLETE")
        self.other = User.objects.create_user(username="interest_other", role="ATHLETE")
        self.viewer_talent = TalentProfile.objects.create(user=self.viewer, talent_category="SCIENCE_TECHNOLOGY")
        self.other_talent = TalentProfile.objects.create(user=self.other, talent_category="SCIENCE_TECHNOLOGY")
        self.ai = TalentDomain.objects.create(name="Artificial Intelligence")
        self.health = TalentDomain.objects.create(name="Mental Health")
        self.other_talent.domains.add(self.ai, self.health)
        RecommendationInterestPreference.objects.create(
            user=self.viewer, inferred_interests_enabled=True
        )

    def test_inference_is_opt_in_and_uses_only_public_activity_topics(self):
        Follow.objects.create(follower=self.viewer, following=self.other)

        inferred = InterestLearningService.inferred_interests(self.viewer)

        self.assertEqual([row["topic"] for row in inferred], ["artificial intelligence"])
        self.assertEqual(inferred[0]["signals"], ["follows"])
        self.assertIn("decay", inferred[0]["explanation"])

        self.other_talent.profile_visibility = "PRIVATE"
        self.other_talent.save(update_fields=("profile_visibility",))
        self.assertEqual(InterestLearningService.inferred_interests(self.viewer), [])

    def test_interest_decay_reduces_the_strength_of_old_activity(self):
        Follow.objects.create(follower=self.viewer, following=self.other)
        recent = InterestLearningService.active_topic_strengths(self.viewer)["artificial intelligence"]
        Follow.objects.filter(follower=self.viewer).update(
            created_at=timezone.now() - timedelta(days=180)
        )
        older = InterestLearningService.active_topic_strengths(self.viewer)["artificial intelligence"]

        self.assertGreater(recent, older)

    def test_likes_saves_applications_and_enrollments_contribute_once_per_item(self):
        post = Post.objects.create(
            author=self.other, talent=self.other_talent, visibility="PUBLIC", caption="Learning update"
        )
        PostLike.objects.create(user=self.viewer, post=post)
        SavedPost.objects.create(user=self.viewer, post=post)

        organization_user = get_user_model().objects.create_user(
            username="interest_org_owner", role="ORGANIZATION"
        )
        organization = Organization.objects.create(
            user=organization_user, name="Interest Learning Org", country="US", status="ACTIVE"
        )
        opportunity = Opportunity.objects.create(
            organization=organization,
            title="AI research role",
            description="Work on artificial intelligence.",
            domain=self.ai,
            active=True,
        )
        Application.objects.create(talent=self.viewer_talent, opportunity=opportunity)
        category = LearningCategory.objects.create(name="Artificial Intelligence")
        course = Course.objects.create(
            creator=self.other,
            category=category,
            title="Artificial Intelligence Basics",
            slug="interest-ai-basics",
            status="APPROVED",
        )
        Enrollment.objects.create(user=self.viewer, course=course)

        row = next(
            interest for interest in InterestLearningService.inferred_interests(self.viewer)
            if interest["topic"] == "artificial intelligence"
        )

        self.assertEqual(
            row["signals"], ["applications", "enrollments", "likes", "saves"]
        )
        # Like + one save + application + enrollment contribute independently.
        self.assertAlmostEqual(row["score"], 10.5, delta=0.15)

    def test_disabling_consent_suppresses_inference_without_mutating_source_activity(self):
        follow = Follow.objects.create(follower=self.viewer, following=self.other)
        preference = InterestLearningService.set_inferred_interests(self.viewer, False)

        self.assertFalse(preference.inferred_interests_enabled)
        self.assertEqual(InterestLearningService.inferred_interests(self.viewer), [])
        self.assertTrue(Follow.objects.filter(pk=follow.pk).exists())

    def test_impressions_are_idempotent_and_private_items_are_rejected(self):
        own_public_post = Post.objects.create(
            author=self.viewer, visibility="PUBLIC", caption="My update"
        )
        private_post = Post.objects.create(
            author=self.other, visibility="PRIVATE", caption="Private update"
        )
        self.client.force_login(self.viewer)
        url = reverse("api:recommendation_impressions")
        payload = {"items": [
            {"kind": "FEED", "item_id": own_public_post.pk},
            {"kind": "FEED", "item_id": own_public_post.pk},
        ]}

        response = self.client.post(url, payload, content_type="application/json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["recorded"], 1)
        self.assertEqual(RecommendationFeedback.objects.filter(
            user=self.viewer, action="IMPRESSION", item_id=own_public_post.pk
        ).count(), 1)
        rejected = self.client.post(url, {
            "kind": "FEED", "item_id": private_post.pk,
        }, content_type="application/json")
        self.assertEqual(rejected.status_code, 400)
        self.assertFalse(RecommendationFeedback.objects.filter(item_id=private_post.pk).exists())

    def test_preference_api_is_authenticated_and_rejects_cross_user_fields(self):
        preferences_url = reverse("api:recommendation_interest_preferences")
        inferred_url = reverse("api:inferred_recommendation_interests")
        self.client.force_login(self.viewer)

        response = self.client.get(preferences_url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["inferred_interests_enabled"])
        rejected = self.client.patch(preferences_url, {
            "user_id": self.other.pk,
            "inferred_interests_enabled": False,
        }, content_type="application/json")
        self.assertEqual(rejected.status_code, 400)
        self.assertTrue(RecommendationInterestPreference.objects.get(
            user=self.viewer
        ).inferred_interests_enabled)

        Follow.objects.create(follower=self.viewer, following=self.other)
        inferred = self.client.get(inferred_url)
        self.assertEqual(inferred.status_code, 200)
        self.assertEqual(inferred.json()["interests"][0]["topic"], "artificial intelligence")
        self.assertNotIn("score", inferred.json()["interests"][0])
        self.client.logout()
        self.assertIn(self.client.get(inferred_url).status_code, (401, 403))

    def test_dismissal_is_unique_and_only_affects_the_authenticated_users_rows(self):
        self.client.force_login(self.viewer)
        response = self.client.post(reverse("api:recommendation_dismissals"), {
            "kind": "TALENT", "item_id": self.other_talent.pk,
        }, content_type="application/json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(RecommendationFeedback.objects.filter(
            user=self.viewer, item_kind="TALENT", action="DISMISSED"
        ).count(), 1)
        self.client.logout()
        self.client.force_login(self.other)
        delete_url = reverse("api:recommendation_dismissal_delete", args=["TALENT", self.other_talent.pk])
        self.assertEqual(self.client.delete(delete_url).status_code, 404)
        self.assertTrue(RecommendationFeedback.objects.filter(
            user=self.viewer, item_kind="TALENT", action="DISMISSED"
        ).exists())

    def test_rollout_disabled_returns_no_inferred_topics(self):
        with override_settings(RECOMMENDATION_INTEREST_LEARNING_ENABLED=False):
            Follow.objects.create(follower=self.viewer, following=self.other)
            self.assertEqual(InterestLearningService.inferred_interests(self.viewer), [])

    def test_feedback_api_does_not_collect_while_rollout_is_disabled(self):
        post = Post.objects.create(author=self.viewer, visibility="PUBLIC", caption="Update")
        self.client.force_login(self.viewer)
        with override_settings(
            RECOMMENDATION_INTEREST_LEARNING_ENABLED=False,
            UNIFIED_RECOMMENDATIONS_ENABLED=False,
        ):
            response = self.client.post(
                reverse("api:recommendation_impressions"),
                {"kind": "FEED", "item_id": post.pk},
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 503)
        self.assertFalse(RecommendationFeedback.objects.exists())

    def test_opted_in_topics_can_adjust_scores_and_dismissed_items_are_filtered(self):
        Follow.objects.create(follower=self.viewer, following=self.other)
        candidate_user = get_user_model().objects.create_user(
            username="interest_candidate", role="ATHLETE"
        )
        candidate = TalentProfile.objects.create(
            user=candidate_user,
            talent_category="SCIENCE_TECHNOLOGY",
            profile_visibility="PUBLIC",
        )
        candidate.domains.add(self.ai)
        service = UnifiedRecommendationService()
        result = {
            "kind": "talent",
            "item": candidate,
            "score": 50.0,
            "matched_topics": [],
            "explanation": "Recommended based on your profile and activity.",
        }

        personalized = service._finalize(self.viewer_talent, "TALENT", [result.copy()])

        self.assertEqual(personalized[0]["score"], 52.0)
        self.assertEqual(personalized[0]["learned_interest_topics"], ["artificial intelligence"])
        self.assertIn("inferred from your activity", personalized[0]["explanation"])

        self.assertTrue(InterestLearningService.record_feedback(
            self.viewer, "TALENT", candidate.pk, "DISMISSED"
        ))
        self.assertEqual(service._finalize(self.viewer_talent, "TALENT", [result.copy()]), [])

    def test_unified_adapter_caches_profile_and_candidate_relation_reads_per_request(self):
        self.viewer_talent.domains.add(self.ai)
        engine = UnifiedRecommendationService().engine
        engine.recommend_sub_ecosystems = lambda user: []
        service = UnifiedRecommendationService(engine)
        candidate = self.other_talent

        with CaptureQueriesContext(connection) as first_pass:
            service._result("talent", self.viewer_talent, candidate, 50)
        with CaptureQueriesContext(connection) as repeated_pass:
            service._result("talent", self.viewer_talent, candidate, 50)

        self.assertEqual(len(first_pass), 4)
        self.assertEqual(len(repeated_pass), 0)

    def test_unified_adapter_uses_prefetched_profile_and_candidate_topics(self):
        self.viewer_talent.domains.add(self.ai)
        viewer = TalentProfile.objects.select_related("user").prefetch_related(
            "domains", "skills"
        ).get(pk=self.viewer_talent.pk)
        candidate = TalentProfile.objects.prefetch_related(
            "domains", "skills"
        ).get(pk=self.other_talent.pk)
        engine = UnifiedRecommendationService().engine
        engine.recommend_sub_ecosystems = lambda user: []
        service = UnifiedRecommendationService(engine)

        with CaptureQueriesContext(connection) as captured:
            service._result("talent", viewer, candidate, 50)

        self.assertEqual(len(captured), 0)

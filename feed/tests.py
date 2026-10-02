from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from events.models import Event, EventCategory
from learning.models import Course, LearningCategory
from organizations.models import Organization
from .models import Post, SavedPost, SharedPost


User = get_user_model()


class FeedAjaxInteractionsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="ajaxuser",
            password="TestPass123!",
        )
        self.post = Post.objects.create(
            author=self.user,
            caption="Test post",
        )
        self.client.force_login(self.user)

    def test_like_post_returns_json_without_redirect(self):
        response = self.client.post(
            f"/feed/like/{self.post.id}/",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["liked"], True)
        self.assertEqual(data["count"], 1)

    def test_comment_post_returns_json_without_redirect(self):
        response = self.client.post(
            f"/feed/comment/{self.post.id}/",
            {"text": "Nice one!"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["comment"]["text"], "Nice one!")
        self.assertEqual(data["count"], 1)

    def test_save_post_returns_json_and_toggles_state(self):
        first_response = self.client.post(
            f"/feed/save/{self.post.id}/",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        second_response = self.client.post(
            f"/feed/save/{self.post.id}/",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertTrue(first_response.json()["saved"])
        self.assertEqual(second_response.status_code, 200)
        self.assertFalse(second_response.json()["saved"])
        self.assertFalse(SavedPost.objects.filter(user=self.user, post=self.post).exists())

    def test_share_post_returns_json_without_redirect(self):
        response = self.client.post(
            f"/feed/share/{self.post.id}/",
            {"caption": "Sharing this"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        self.assertEqual(response.json()["count"], 1)
        self.assertTrue(
            SharedPost.objects.filter(
                user=self.user,
                post=self.post,
                caption="Sharing this",
            ).exists()
        )

    def test_like_and_comment_event_in_feed(self):
        organization = Organization.objects.create(
            name="Test Org",
            country="Nigeria",
            city="Lagos",
            email="org@example.com",
            website="https://example.com",
            description="Org",
            official=True,
        )
        category = EventCategory.objects.create(name="Sports")
        event = Event.objects.create(
            organizer=organization,
            category=category,
            title="Community Cup",
            slug="community-cup",
            description="Test event",
            event_type="WORKSHOP",
            location="Lagos",
            online=False,
            start_date=timezone.now() + timedelta(days=2),
            end_date=timezone.now() + timedelta(days=3),
            registration_deadline=timezone.now() + timedelta(days=1),
        )

        like_response = self.client.post(
            f"/events/{event.id}/like/",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(like_response.status_code, 200)
        self.assertEqual(like_response.json()["count"], 1)

        comment_response = self.client.post(
            f"/events/{event.id}/comment/",
            {"text": "Amazing event!"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(comment_response.status_code, 200)
        self.assertEqual(comment_response.json()["count"], 1)

    def test_like_and_comment_course_in_feed(self):
        category = LearningCategory.objects.create(name="Football")
        course = Course.objects.create(
            creator=self.user,
            category=category,
            title="Football Basics",
            slug="football-basics",
            description="Learn the basics.",
            duration=30,
            status="APPROVED",
        )

        like_response = self.client.post(
            f"/learning/course/{course.id}/like/",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(like_response.status_code, 200)
        self.assertEqual(like_response.json()["count"], 1)

        comment_response = self.client.post(
            f"/learning/course/{course.id}/comment/",
            {"text": "Very helpful!"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(comment_response.status_code, 200)
        self.assertEqual(comment_response.json()["count"], 1)

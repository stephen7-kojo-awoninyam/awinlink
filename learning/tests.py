from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from learning.models import Course, LearningCategory


User = get_user_model()


class CourseModerationAndResubmissionTests(APITestCase):
    def setUp(self):
        self.creator = User.objects.create_user(
            username="course_creator", password="TestPass123!", role="ATHLETE"
        )
        self.other_creator = User.objects.create_user(
            username="other_course_creator", password="TestPass123!", role="COACH"
        )
        self.admin = User.objects.create_user(
            username="course_admin", password="TestPass123!", role="ADMIN"
        )
        self.category = LearningCategory.objects.create(name="Test Learning")
        self.pending_course = self.create_course(
            creator=self.creator, title="Pending course", slug="pending-course", status="PENDING"
        )
        self.rejected_course = self.create_course(
            creator=self.creator,
            title="Rejected course",
            slug="rejected-course",
            status="REJECTED",
            rejection_reason="Add more lesson detail.",
        )
        self.pending_url = "/api/learning/courses/pending/"

    def create_course(self, *, creator, title, slug, status, rejection_reason=""):
        return Course.objects.create(
            creator=creator,
            category=self.category,
            title=title,
            slug=slug,
            description="Course description",
            status=status,
            rejection_reason=rejection_reason,
        )

    def test_admin_can_list_only_pending_courses(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.pending_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.data], [self.pending_course.id])

    def test_non_admin_cannot_read_moderation_queue_or_moderate(self):
        self.client.force_authenticate(user=self.creator)
        queue_response = self.client.get(self.pending_url)
        approve_response = self.client.post(
            f"/api/learning/courses/{self.pending_course.id}/approve/", {}, format="json"
        )
        self.assertEqual(queue_response.status_code, 403)
        self.assertEqual(approve_response.status_code, 403)
        self.pending_course.refresh_from_db()
        self.assertEqual(self.pending_course.status, "PENDING")

    def test_admin_can_approve_or_reject_pending_courses(self):
        self.client.force_authenticate(user=self.admin)
        course_to_reject = self.create_course(
            creator=self.other_creator,
            title="Course to reject",
            slug="course-to-reject",
            status="PENDING",
        )
        approved = self.client.post(
            f"/api/learning/courses/{self.pending_course.id}/approve/", {}, format="json"
        )
        rejected = self.client.post(
            f"/api/learning/courses/{course_to_reject.id}/reject/",
            {"rejection_reason": "Needs revision."},
            format="json",
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.data["status"], "APPROVED")
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.data["status"], "REJECTED")

    def test_rejection_requires_reason(self):
        self.client.force_authenticate(user=self.admin)
        course = self.create_course(
            creator=self.other_creator,
            title="Another pending course",
            slug="another-pending-course",
            status="PENDING",
        )
        response = self.client.post(
            f"/api/learning/courses/{course.id}/reject/", {}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        course.refresh_from_db()
        self.assertEqual(course.status, "PENDING")

    def test_creator_can_edit_rejected_course_and_resubmit(self):
        self.client.force_authenticate(user=self.creator)
        update = self.client.patch(
            f"/api/learning/courses/{self.rejected_course.id}/",
            {"title": "Revised course", "description": "Revised description"},
            format="json",
        )
        self.assertEqual(update.status_code, 200)
        self.assertEqual(update.data["status"], "REJECTED")

        submit = self.client.post(
            f"/api/learning/courses/{self.rejected_course.id}/submit/", {}, format="json"
        )
        self.assertEqual(submit.status_code, 200)
        self.assertEqual(submit.data["status"], "PENDING")
        self.rejected_course.refresh_from_db()
        self.assertEqual(self.rejected_course.title, "Revised course")
        self.assertEqual(self.rejected_course.rejection_reason, "")

    def test_non_creator_cannot_edit_course_and_pending_course_is_locked(self):
        self.client.force_authenticate(user=self.other_creator)
        denied = self.client.patch(
            f"/api/learning/courses/{self.rejected_course.id}/",
            {"title": "Unauthorized"},
            format="json",
        )
        self.assertEqual(denied.status_code, 403)

        self.client.force_authenticate(user=self.creator)
        locked = self.client.patch(
            f"/api/learning/courses/{self.pending_course.id}/",
            {"title": "Should stay pending"},
            format="json",
        )
        self.assertEqual(locked.status_code, 400)

"""Free-only Learning authoring and publication gates preserve legacy data."""
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from rest_framework.test import APITestCase

from .admin import CourseAdminForm
from .models import Course, Enrollment, LearningCategory


class LearningFreeLaunchTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.creator = User.objects.create_user(username="free-launch-creator", role="COACH")
        self.learner = User.objects.create_user(username="free-launch-learner", role="ATHLETE")
        self.admin = User.objects.create_user(username="free-launch-admin", role="ADMIN", is_staff=True)
        self.category = LearningCategory.objects.create(name="Free launch")
        self.client.force_authenticate(self.creator)

    def test_web_and_api_create_only_free_courses_even_if_client_submits_paid_flag(self):
        rejected = self.client.post("/api/learning/courses/create/", {
            "title": "Paid API draft", "slug": "paid-api-draft", "description": "Not supported",
            "category": self.category.pk, "is_free": False,
        }, format="json")
        self.assertEqual(rejected.status_code, 400)
        self.assertFalse(Course.objects.filter(slug="paid-api-draft").exists())

        created = self.client.post("/api/learning/courses/create/", {
            "title": "Free API draft", "slug": "free-api-draft", "description": "Available at launch",
            "category": self.category.pk,
        }, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertTrue(Course.objects.get(pk=created.data["id"]).is_free)

        browser = Client()
        browser.force_login(self.creator)
        response = browser.post(reverse("create_course"), {
            "title": "Free web draft", "slug": "free-web-draft", "description": "Available at launch",
            "category": self.category.pk, "level": "BEGINNER", "duration": 30, "is_free": "false",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Course.objects.get(slug="free-web-draft").is_free)

    def test_paid_course_status_is_immutable_and_existing_enrollment_is_preserved(self):
        paid = Course.objects.create(creator=self.creator, category=self.category, title="Legacy paid",
            slug="legacy-paid", description="Preserve as-is", is_free=False, status="DRAFT")
        enrollment = Enrollment.objects.create(user=self.learner, course=paid)

        changed = self.client.patch(f"/api/learning/courses/{paid.pk}/", {"title": "Changed", "is_free": True}, format="json")
        self.assertEqual(changed.status_code, 400)
        self.assertEqual(self.client.post(f"/api/learning/courses/{paid.pk}/submit/").status_code, 400)
        paid.refresh_from_db()
        self.assertEqual((paid.title, paid.is_free, paid.status), ("Legacy paid", False, "DRAFT"))
        self.assertTrue(Enrollment.objects.filter(pk=enrollment.pk, course=paid, user=self.learner).exists())

    def test_direct_admin_approval_path_rejects_paid_courses_without_mutating_them(self):
        paid = Course.objects.create(creator=self.creator, category=self.category, title="Pending paid",
            slug="pending-paid", description="Preserve moderation history", is_free=False, status="PENDING")
        enrollment = Enrollment.objects.create(user=self.learner, course=paid)
        self.client.force_authenticate(self.admin)

        response = self.client.post(f"/api/learning/courses/{paid.pk}/approve/")
        self.assertEqual(response.status_code, 400)
        paid.refresh_from_db()
        self.assertEqual((paid.is_free, paid.status), (False, "PENDING"))
        self.assertTrue(Enrollment.objects.filter(pk=enrollment.pk).exists())

        form = CourseAdminForm(data={
            "creator": self.creator.pk, "category": self.category.pk, "title": "Admin paid",
            "slug": "admin-paid", "description": "Not supported", "level": "BEGINNER",
            "duration": 10, "is_free": "false", "status": "APPROVED", "rejection_reason": "",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("is_free", form.errors)

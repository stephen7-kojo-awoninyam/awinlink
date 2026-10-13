from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from learning.models import Course, LearningCategory
from talents.models import TalentProfile


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class ExploreRegressionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="explore_viewer")
        cls.category = LearningCategory.objects.create(name="Explore Learning")

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("explore")

    def course(self, status, title, *, created_at=None):
        course = Course.objects.create(
            creator=self.user, category=self.category, title=title,
            slug=title.lower().replace("_", "-"), description=title,
            status=status,
        )
        if created_at is not None:
            Course.objects.filter(pk=course.pk).update(created_at=created_at)
        return course

    def test_authenticated_explore_renders_new_ui_without_courses(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/explore.html")
        self.assertContains(response, "data-discovery-page")
        self.assertContains(response, "No learning content available right now.")
        self.assertEqual(list(response.context["learning_content"]), [])

    def test_only_approved_courses_are_published_on_explore(self):
        approved = self.course("APPROVED", "APPROVED_COURSE_MARKER")
        for status, _ in Course.STATUS:
            if status != "APPROVED":
                self.course(status, f"{status}_COURSE_MARKER")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["learning_content"]), [approved])
        self.assertContains(response, approved.title)
        for status, _ in Course.STATUS:
            if status != "APPROVED":
                self.assertNotContains(response, f"{status}_COURSE_MARKER")

    def test_publication_filter_keeps_newest_eight_courses_in_order(self):
        start = timezone.now() - timedelta(days=30)
        approved = [self.course("APPROVED", f"APPROVED_COURSE_{index}", created_at=start + timedelta(days=index)) for index in range(10)]
        self.course("PENDING", "NEWER_PENDING_COURSE", created_at=timezone.now())
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["learning_content"]), list(reversed(approved[2:])))
        self.assertNotContains(response, "NEWER_PENDING_COURSE")
        self.assertNotContains(response, approved[0].title)
        self.assertNotContains(response, approved[1].title)

    def test_creator_and_admin_cannot_publish_draft_courses_through_explore(self):
        self.course("DRAFT", "OWN_DRAFT_COURSE_MARKER")
        self.course("REJECTED", "OWN_REJECTED_COURSE_MARKER")
        get_user_model().objects.filter(pk=self.user.pk).update(role="ADMIN", is_superuser=True)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["learning_content"]), [])
        self.assertNotContains(response, "OWN_DRAFT_COURSE_MARKER")
        self.assertNotContains(response, "OWN_REJECTED_COURSE_MARKER")

    def test_login_requirement_is_preserved(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertRedirects(response, f"{reverse('login')}?next={self.url}", fetch_redirect_response=False)

    def test_explore_remains_available_to_all_authenticated_account_roles(self):
        for role, _ in get_user_model().ROLE_CHOICES:
            with self.subTest(role=role):
                get_user_model().objects.filter(pk=self.user.pk).update(role=role)
                response = self.client.get(self.url)
                self.assertEqual(response.status_code, 200)

    def test_featured_profile_privacy_and_category_controls_are_preserved(self):
        public_user = get_user_model().objects.create_user(username="explore_public")
        private_user = get_user_model().objects.create_user(username="explore_private")
        restricted_user = get_user_model().objects.create_user(username="explore_restricted")
        TalentProfile.objects.create(user=public_user, verified=True, profile_visibility="PUBLIC", headline="PUBLIC_FEATURED_MARKER")
        TalentProfile.objects.create(user=private_user, verified=True, profile_visibility="PRIVATE", headline="PRIVATE_FEATURED_MARKER", biography="PRIVATE_BIO_MARKER")
        TalentProfile.objects.create(user=restricted_user, verified=True, profile_visibility="ORGANIZATIONS", headline="ORG_FEATURED_MARKER")
        TalentProfile.objects.create(user=self.user, verified=True, profile_visibility="PRIVATE", headline="OWN_FEATURED_MARKER")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PUBLIC_FEATURED_MARKER")
        self.assertContains(response, "OWN_FEATURED_MARKER")
        for marker in ("PRIVATE_FEATURED_MARKER", "PRIVATE_BIO_MARKER", "ORG_FEATURED_MARKER"):
            self.assertNotContains(response, marker)
        for category in ("SPORTS", "SCIENCE_TECHNOLOGY", "ARTS", "OTHERS"):
            self.assertContains(response, f'data-discovery-category="{category}"')

from importlib import import_module
from io import StringIO
from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import TestCase

from .category_seeds import COURSE_CATEGORIES
from .forms import CourseForm
from .models import Course, LearningCategory


class CreatorCategoryDefaultTests(TestCase):
    def test_all_profile_categories_default_on_web_and_mobile_api(self):
        from coaches.models import CoachProfile
        from scouts.models import ScoutProfile
        from talents.models import TalentProfile
        from rest_framework.test import APIRequestFactory, force_authenticate
        from .api_views import LearningCategoryListAPIView
        from .views import create_course
        from django.test import RequestFactory
        from unittest.mock import patch

        for role, model, field in (("COACH", CoachProfile, "coach_category"),
                                   ("SCOUT", ScoutProfile, "scout_category"),
                                   ("ATHLETE", TalentProfile, "talent_category")):
            user = get_user_model().objects.create_user(username=f"default-{role}", role=role)
            profile = model.objects.create(user=user)
            for code, name in (("SPORTS", "Sports"), ("SCIENCE_TECHNOLOGY", "Science and technology"),
                               ("ARTS", "Arts"), ("OTHERS", "Others")):
                setattr(profile, field, code)
                profile.save()
                expected = LearningCategory.objects.get(name=name).pk
                # Fetch a fresh user to avoid stale reverse relation caches.
                user = get_user_model().objects.get(pk=user.pk)
                request = RequestFactory().get("/learning/create/")
                request.user = user
                with patch("learning.views.render") as render:
                    create_course(request)
                self.assertEqual(render.call_args.args[2]["form"].initial["category"], expected)
                request = APIRequestFactory().get("/api/learning/categories/")
                force_authenticate(request, user=user)
                response = LearningCategoryListAPIView.as_view()(request)
                self.assertEqual([item["id"] for item in response.data if item["is_default"]], [expected])

    def test_override_validation_and_existing_course_are_preserved(self):
        from coaches.models import CoachProfile
        user = get_user_model().objects.create_user(username="override-coach", role="COACH")
        CoachProfile.objects.create(user=user, coach_category="SPORTS")
        arts = LearningCategory.objects.get(name="Arts")
        data = {"category": arts.pk, "title": "Changed", "slug": "changed",
                "description": "Learn", "level": "BEGINNER", "duration": 1}
        form = CourseForm(data=data, creator=user)
        self.assertTrue(form.is_valid(), form.errors)
        course = form.save(commit=False)
        course.creator = user
        course.save()
        self.assertEqual(course.category_id, arts.pk)
        self.assertEqual(CourseForm(instance=course, creator=user).initial["category"], arts.pk)
        invalid = CourseForm(data={**data, "title": ""}, creator=user)
        self.assertFalse(invalid.is_valid())
        self.assertEqual(int(invalid["category"].value()), arts.pk)
        missing = CourseForm(data={**data, "category": ""}, creator=user)
        self.assertFalse(missing.is_valid())
        self.assertIn("category", missing.errors)

    def test_missing_profile_unset_category_and_missing_seed_have_no_default(self):
        from coaches.models import CoachProfile
        user = get_user_model().objects.create_user(username="no-default", role="COACH")
        self.assertNotIn("category", CourseForm(creator=user).initial)
        profile = CoachProfile.objects.create(user=user)
        user = get_user_model().objects.get(pk=user.pk)
        self.assertNotIn("category", CourseForm(creator=user).initial)
        profile.coach_category = "ARTS"
        profile.save()
        LearningCategory.objects.get(name="Arts").delete()
        user = get_user_model().objects.get(pk=user.pk)
        self.assertNotIn("category", CourseForm(creator=user).initial)


class CourseCategoryTests(TestCase):
    def test_migration_populates_fresh_database(self):
        for name, _ in COURSE_CATEGORIES:
            self.assertTrue(LearningCategory.objects.filter(name=name).exists())

    def test_seed_and_migration_preserve_existing_courses_and_category_metadata(self):
        category = LearningCategory.objects.get(name="Sports")
        category.description = "Our existing description"
        category.save()
        custom = LearningCategory.objects.create(name="Local specialty")
        user = get_user_model().objects.create_user(username="category-coach", role="COACH")
        for index, item in enumerate((category, custom)):
            Course.objects.create(creator=user, category=item, title="Existing course",
                                  slug=f"existing-{index}", description="Keep me", status="APPROVED")
        before = list(Course.objects.order_by("pk").values())
        LearningCategory.objects.get(name="Arts").delete()
        for _ in range(2):
            call_command("seed_course_categories", stdout=StringIO())
        migration = import_module("learning.migrations.0014_seed_course_categories")
        migration.seed_categories(apps, SimpleNamespace(connection=connection))
        self.assertEqual(list(Course.objects.order_by("pk").values()), before)
        category.refresh_from_db()
        self.assertEqual(category.description, "Our existing description")
        self.assertTrue(LearningCategory.objects.filter(pk=custom.pk).exists())
        self.assertEqual(LearningCategory.objects.count(), 5)

    def test_dropdown_contains_categories_and_retains_selection_after_error(self):
        for name, _ in COURSE_CATEGORIES:
            category = LearningCategory.objects.get(name=name)
            form = CourseForm(data={"category": category.pk})
            self.assertFalse(form.is_valid())
            self.assertInHTML(f'<option value="{category.pk}" selected>{name}</option>',
                              str(form["category"]))
        self.assertIn("Select a course category", str(CourseForm()["category"]))

    def test_form_accepts_each_category_and_rejects_missing_or_unknown_category(self):
        data = {"title": "New course", "slug": "new-course", "description": "Learn",
                "level": "BEGINNER", "duration": 30, "is_free": True}
        for name, _ in COURSE_CATEGORIES:
            category = LearningCategory.objects.get(name=name)
            form = CourseForm(data={**data, "category": category.pk})
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(form.save(commit=False).category_id, category.pk)
        for value in ("", "999999", "invalid"):
            form = CourseForm(data={**data, "category": value})
            self.assertFalse(form.is_valid())
            self.assertIn("category", form.errors)

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from talents.models import TalentProfile

from .models import (
    CoachProfile,
    CoachTalentBookmark,
    CoachTalentFollow,
    CoachTalentView,
)


class CoachTalentVisibilityTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.coach_user = user_model.objects.create_user(
            username="coach",
            password="test-password",
            role="COACH",
        )
        self.coach = CoachProfile.objects.create(
            user=self.coach_user,
            coach_category="SPORTS",
        )
        self.public_talent = self.create_talent(
            "public_talent",
            "PUBLIC",
        )
        self.organization_talent = self.create_talent(
            "organization_talent",
            "ORGANIZATIONS",
        )
        self.private_talent = self.create_talent(
            "private_talent",
            "PRIVATE",
        )
        self.api_client = APIClient()
        self.api_client.force_authenticate(user=self.coach_user)

    @staticmethod
    def create_talent(username, visibility):
        user = get_user_model().objects.create_user(username=username)
        return TalentProfile.objects.create(
            user=user,
            profile_visibility=visibility,
        )

    @override_settings(
        STORAGES={
            "default": {
                "BACKEND": "django.core.files.storage.FileSystemStorage",
            },
            "staticfiles": {
                "BACKEND": (
                    "django.contrib.staticfiles.storage.StaticFilesStorage"
                ),
            },
        }
    )
    def test_web_directory_only_lists_public_profiles(self):
        self.client.force_login(self.coach_user)

        for path in ("/coaches/talents/", "/coaches/talent-directory/"):
            with self.subTest(path=path):
                response = self.client.get(path)

                self.assertEqual(response.status_code, 200)
                listed_ids = {
                    talent.pk
                    for talent in response.context["talents"]
                }
                self.assertEqual(listed_ids, {self.public_talent.pk})

    def test_web_profile_page_hides_non_public_profiles(self):
        self.client.force_login(self.coach_user)

        for talent in (self.organization_talent, self.private_talent):
            with self.subTest(visibility=talent.profile_visibility):
                response = self.client.get(
                    reverse("coach_view_talent", args=[talent.pk])
                )

                self.assertEqual(response.status_code, 404)

        self.assertFalse(
            CoachTalentView.objects.filter(coach=self.coach).exists()
        )

    def test_api_directory_only_lists_public_profiles(self):
        response = self.api_client.get(
            reverse("coaches_api:coach_talent_list")
        )

        self.assertEqual(response.status_code, 200)
        rows = (
            response.data["results"]
            if isinstance(response.data, dict)
            else response.data
        )
        listed_ids = {row["id"] for row in rows}
        self.assertEqual(listed_ids, {self.public_talent.pk})

    def test_api_cannot_view_follow_or_bookmark_non_public_profiles(self):
        for talent in (self.organization_talent, self.private_talent):
            with self.subTest(visibility=talent.profile_visibility):
                response = self.api_client.post(
                    reverse(
                        "coaches_api:view_talent",
                        args=[talent.pk],
                    )
                )
                self.assertEqual(response.status_code, 404)

                response = self.api_client.post(
                    reverse(
                        "coaches_api:follow_talent",
                        args=[talent.pk],
                    )
                )
                self.assertEqual(response.status_code, 404)

                response = self.api_client.post(
                    reverse(
                        "coaches_api:bookmark_talent",
                        args=[talent.pk],
                    )
                )
                self.assertEqual(response.status_code, 404)

        self.assertFalse(
            CoachTalentView.objects.filter(coach=self.coach).exists()
        )
        self.assertFalse(
            CoachTalentFollow.objects.filter(coach=self.coach).exists()
        )
        self.assertFalse(
            CoachTalentBookmark.objects.filter(coach=self.coach).exists()
        )

    def test_api_tracking_lists_hide_profiles_that_became_non_public(self):
        CoachTalentView.objects.create(
            coach=self.coach,
            talent=self.private_talent,
        )
        public_view = CoachTalentView.objects.create(
            coach=self.coach,
            talent=self.public_talent,
        )
        CoachTalentFollow.objects.create(
            coach=self.coach,
            talent=self.private_talent,
        )
        public_follow = CoachTalentFollow.objects.create(
            coach=self.coach,
            talent=self.public_talent,
        )
        private_bookmark = CoachTalentBookmark.objects.create(
            coach=self.coach,
            talent=self.private_talent,
        )
        public_bookmark = CoachTalentBookmark.objects.create(
            coach=self.coach,
            talent=self.public_talent,
        )

        endpoints = (
            ("coaches_api:my_talent_views", "talent", public_view),
            ("coaches_api:followed_talents", "talent", public_follow),
            ("coaches_api:my_bookmarks", "talent", public_bookmark),
        )
        for endpoint, relation_field, public_record in endpoints:
            with self.subTest(endpoint=endpoint):
                response = self.api_client.get(reverse(endpoint))
                self.assertEqual(response.status_code, 200)
                rows = (
                    response.data["results"]
                    if isinstance(response.data, dict)
                    else response.data
                )
                self.assertEqual(len(rows), 1)
                self.assertEqual(
                    rows[0][relation_field],
                    public_record.talent_id,
                )

        response = self.api_client.patch(
            reverse(
                "coaches_api:bookmark_update",
                args=[private_bookmark.pk],
            ),
            {"notes": "Updated note"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
    def test_api_coach_profile_exposes_and_updates_coach_category(self):
        response = self.api_client.get(
            reverse("coaches_api:my_coach_profile")
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["coach_category"], "SPORTS")

        response = self.api_client.patch(
            reverse("coaches_api:my_coach_profile_update"),
            {"coach_category": "ARTS"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["coach_category"], "ARTS")
        self.coach.refresh_from_db()
        self.assertEqual(self.coach.coach_category, "ARTS")

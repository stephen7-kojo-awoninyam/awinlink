from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from talents.models import TalentProfile

from .models import (
    ScoutProfile,
    ScoutTalentBookmark,
    ScoutTalentFollow,
    ScoutTalentView,
)


class ScoutTalentAccessTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.scout_user = user_model.objects.create_user(
            username="scout",
            password="test-password",
            role="SCOUT",
        )
        self.scout = ScoutProfile.objects.create(
            user=self.scout_user,
            scout_category="SPORTS",
        )
        self.public_talent = self.create_talent("public_talent", "PUBLIC")
        self.organization_talent = self.create_talent(
            "organization_talent",
            "ORGANIZATIONS",
        )
        self.private_talent = self.create_talent("private_talent", "PRIVATE")
        self.api_client = APIClient()
        self.api_client.force_authenticate(user=self.scout_user)

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
    def test_web_directory_only_shows_public_talents(self):
        self.client.force_login(self.scout_user)
        response = self.client.get(reverse("scout_talent_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {talent.pk for talent in response.context["talents"]},
            {self.public_talent.pk},
        )

    def test_non_public_profiles_cannot_be_viewed_or_tracked(self):
        self.client.force_login(self.scout_user)

        for talent in (self.organization_talent, self.private_talent):
            with self.subTest(visibility=talent.profile_visibility):
                response = self.client.get(
                    reverse("scout_talent_detail", args=[talent.pk])
                )
                self.assertEqual(response.status_code, 404)

        self.assertFalse(
            ScoutTalentView.objects.filter(scout=self.scout).exists()
        )

    def test_follow_bookmark_and_note_updates_require_post(self):
        self.client.force_login(self.scout_user)
        follow_url = reverse("follow_talent", args=[self.public_talent.pk])
        bookmark_url = reverse("bookmark_talent", args=[self.public_talent.pk])
        remove_url = reverse("remove_bookmark", args=[self.public_talent.pk])
        notes_url = reverse(
            "update_bookmark_notes",
            args=[self.public_talent.pk],
        )

        for url in (follow_url, bookmark_url, remove_url, notes_url):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 405)

        self.assertFalse(
            ScoutTalentFollow.objects.filter(scout=self.scout).exists()
        )
        self.assertFalse(
            ScoutTalentBookmark.objects.filter(scout=self.scout).exists()
        )

    def test_web_actions_reject_non_public_talents(self):
        self.client.force_login(self.scout_user)

        for talent in (self.organization_talent, self.private_talent):
            with self.subTest(visibility=talent.profile_visibility):
                for route_name in ("follow_talent", "bookmark_talent"):
                    response = self.client.post(
                        reverse(route_name, args=[talent.pk])
                    )
                    self.assertEqual(response.status_code, 404)

        self.assertFalse(
            ScoutTalentFollow.objects.filter(scout=self.scout).exists()
        )
        self.assertFalse(
            ScoutTalentBookmark.objects.filter(scout=self.scout).exists()
        )

    def test_api_directory_returns_only_public_talent_profiles(self):
        response = self.api_client.get(
            reverse("scouts_api:scout_talent_list")
        )

        self.assertEqual(response.status_code, 200)
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(
            {row["id"] for row in rows},
            {self.public_talent.pk},
        )

    def test_api_actions_reject_non_public_talents(self):
        for talent in (self.organization_talent, self.private_talent):
            with self.subTest(visibility=talent.profile_visibility):
                for route_name in (
                    "view_talent",
                    "follow_talent",
                    "bookmark_talent",
                ):
                    response = self.api_client.post(
                        reverse(
                            f"scouts_api:{route_name}",
                            args=[talent.pk],
                        )
                    )
                    self.assertEqual(response.status_code, 404)

        self.assertFalse(
            ScoutTalentView.objects.filter(scout=self.scout).exists()
        )
        self.assertFalse(
            ScoutTalentFollow.objects.filter(scout=self.scout).exists()
        )
        self.assertFalse(
            ScoutTalentBookmark.objects.filter(scout=self.scout).exists()
        )

    def test_api_tracking_lists_hide_profiles_that_are_not_public(self):
        ScoutTalentView.objects.create(
            scout=self.scout,
            talent=self.private_talent,
        )
        ScoutTalentView.objects.create(
            scout=self.scout,
            talent=self.public_talent,
        )
        ScoutTalentFollow.objects.create(
            scout=self.scout,
            talent=self.private_talent,
        )
        ScoutTalentFollow.objects.create(
            scout=self.scout,
            talent=self.public_talent,
        )
        private_bookmark = ScoutTalentBookmark.objects.create(
            scout=self.scout,
            talent=self.private_talent,
        )
        ScoutTalentBookmark.objects.create(
            scout=self.scout,
            talent=self.public_talent,
        )

        for endpoint in (
            "scouts_api:my_talent_views",
            "scouts_api:followed_talents",
            "scouts_api:my_bookmarks",
        ):
            with self.subTest(endpoint=endpoint):
                response = self.api_client.get(reverse(endpoint))
                rows = (
                    response.data["results"]
                    if isinstance(response.data, dict)
                    else response.data
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["talent"], self.public_talent.pk)

        response = self.api_client.patch(
            reverse(
                "scouts_api:bookmark_update",
                args=[private_bookmark.pk],
            ),
            {"notes": "Private update"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_scout_profile_api_includes_and_updates_category(self):
        response = self.api_client.get(
            reverse("scouts_api:my_scout_profile")
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["scout_category"], "SPORTS")

        response = self.api_client.patch(
            reverse("scouts_api:my_scout_profile_update"),
            {"scout_category": "ARTS"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["scout_category"], "ARTS")
        self.scout.refresh_from_db()
        self.assertEqual(self.scout.scout_category, "ARTS")

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
    def test_new_scout_can_select_category_and_create_profile(self):
        new_scout_user = get_user_model().objects.create_user(
            username="new_scout",
            password="test-password",
            role="SCOUT",
        )
        self.client.force_login(new_scout_user)

        category_response = self.client.post(
            reverse("select_scout_category"),
            {"scout_category": "SPORTS"},
        )

        self.assertRedirects(
            category_response,
            reverse("create_scout_profile"),
        )

        profile_page = self.client.get(reverse("create_scout_profile"))
        self.assertEqual(profile_page.status_code, 200)
        self.assertContains(profile_page, "Create Scout Profile")

        create_response = self.client.post(
            reverse("create_scout_profile"),
            {
                "headline": "Sports Talent Scout",
                "biography": "Finds and supports emerging athletes.",
                "specialization": "Football",
                "country": "Ghana",
                "city": "Accra",
                "organization": "",
            },
        )

        self.assertRedirects(
            create_response,
            reverse("scout_dashboard"),
        )
        scout_profile = ScoutProfile.objects.get(user=new_scout_user)
        self.assertEqual(scout_profile.scout_category, "SPORTS")
        self.assertEqual(scout_profile.headline, "Sports Talent Scout")
        self.assertEqual(scout_profile.specialization, "Football")

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
    def test_dashboard_uses_scout_profile_setup_route(self):
        self.client.force_login(self.scout_user)
        response = self.client.get(reverse("scout_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit Scout Profile")

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.test import override_settings

from coaches.models import CoachProfile
from organizations.models import Organization
from scouts.models import ScoutProfile
from talents.models import TalentProfile


@override_settings(
    STORAGES={
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
)
class UsernameSearchTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.talent_user = user_model.objects.create_user(
            username="talent_handle",
            password="test-password",
            role="ATHLETE",
        )
        self.talent = TalentProfile.objects.create(
            user=self.talent_user,
            profile_visibility="PUBLIC",
        )

        self.private_talent_user = user_model.objects.create_user(
            username="private_handle",
            password="test-password",
            role="ATHLETE",
        )
        TalentProfile.objects.create(
            user=self.private_talent_user,
            profile_visibility="PRIVATE",
        )

        self.organization_talent_user = user_model.objects.create_user(
            username="organization_talent",
            password="test-password",
            role="ATHLETE",
        )
        TalentProfile.objects.create(
            user=self.organization_talent_user,
            profile_visibility="ORGANIZATIONS",
        )

        self.coach_user = user_model.objects.create_user(
            username="coach_handle",
            password="test-password",
            role="COACH",
        )
        CoachProfile.objects.create(
            user=self.coach_user,
            coach_category="SPORTS",
            specialization="Football",
        )

        self.scout_user = user_model.objects.create_user(
            username="scout_handle",
            password="test-password",
            role="SCOUT",
        )
        ScoutProfile.objects.create(
            user=self.scout_user,
            scout_category="ARTS",
        )

        self.organization_user = user_model.objects.create_user(
            username="organization_handle",
            password="test-password",
            role="ORGANIZATION",
        )
        Organization.objects.create(
            user=self.organization_user,
            name="Awinlink Academy",
            country="Ghana",
        )
        user_model.objects.create_user(
            username="admin_handle",
            password="test-password",
            role="ADMIN",
            is_superuser=True,
        )

    def test_at_username_finds_each_public_account_type(self):
        expected_accounts = (
            ("talent_handle", "Athlete"),
            ("coach_handle", "Coach"),
            ("scout_handle", "Scout"),
            ("organization_handle", "Organization"),
        )

        for username, role_label in expected_accounts:
            with self.subTest(username=username):
                response = self.client.get(
                    "/search/",
                    {"search": f"@{username}"},
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(response.context["user_results"]), 1)
                self.assertEqual(
                    response.context["user_results"][0]["role_label"],
                    role_label,
                )
                self.assertTemplateUsed(response, "search/search.html")

    def test_at_username_is_case_insensitive_and_exact(self):
        response = self.client.get(
            "/search/",
            {"search": "@COACH_HANDLE"},
        )

        self.assertEqual(len(response.context["user_results"]), 1)
        self.assertEqual(
            response.context["user_results"][0]["user"],
            self.coach_user,
        )

        response = self.client.get(
            "/search/",
            {"search": "@coach"},
        )
        self.assertEqual(response.context["user_results"], [])

    def test_at_username_respects_talent_profile_visibility(self):
        private_response = self.client.get(
            "/search/",
            {"search": "@private_handle"},
        )
        self.assertEqual(private_response.context["user_results"], [])

        organization_response = self.client.get(
            "/search/",
            {"search": "@organization_talent"},
        )
        self.assertEqual(organization_response.context["user_results"], [])

        organization_user = get_user_model().objects.get(
            username="organization_handle",
        )
        self.client.force_login(organization_user)

        organization_response = self.client.get(
            "/search/",
            {"search": "@organization_talent"},
        )
        self.assertEqual(len(organization_response.context["user_results"]), 1)

        self.client.force_login(self.private_talent_user)
        owner_response = self.client.get(
            "/search/",
            {"search": "@private_handle"},
        )
        self.assertEqual(len(owner_response.context["user_results"]), 1)

    def test_at_username_does_not_list_admin_accounts(self):
        response = self.client.get(
            "/search/",
            {"search": "@admin_handle"},
        )
        self.assertEqual(response.context["user_results"], [])

    def test_global_search_has_search_url_and_existing_talent_search_still_works(self):
        self.client.force_login(self.talent_user)
        response = self.client.get("/search/", {"search": "talent"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="globalSearch"')
        self.assertContains(response, 'data-search-url="/search/"')
        self.assertContains(response, self.talent_user.username)

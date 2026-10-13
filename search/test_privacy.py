from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from analytics.models import TalentProfileView
from organizations.models import Organization
from talents.models import TalentProfile


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class TalentSearchPrivacyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.public_user = User.objects.create_user(username="privacy_public")
        cls.org_talent_user = User.objects.create_user(username="privacy_org_talent")
        cls.private_user = User.objects.create_user(username="privacy_private")
        cls.public = TalentProfile.objects.create(
            user=cls.public_user, profile_visibility="PUBLIC",
            headline="PUBLIC_PROFILE_MARKER", availability_status="AVAILABLE",
        )
        cls.org_talent = TalentProfile.objects.create(
            user=cls.org_talent_user, profile_visibility="ORGANIZATIONS",
            headline="ORG_ONLY_PROFILE_MARKER", availability_status="AVAILABLE",
        )
        cls.private = TalentProfile.objects.create(
            user=cls.private_user, profile_visibility="PRIVATE",
            headline="PRIVATE_PROFILE_MARKER", availability_status="AVAILABLE",
        )
        cls.ordinary = User.objects.create_user(username="privacy_ordinary")
        cls.coach = User.objects.create_user(username="privacy_coach", role="COACH")
        cls.scout = User.objects.create_user(username="privacy_scout", role="SCOUT")
        cls.admin = User.objects.create_user(
            username="privacy_admin", role="ADMIN", is_superuser=True,
        )
        cls.active_owner = User.objects.create_user(
            username="privacy_active_owner", role="ORGANIZATION",
        )
        cls.active_org = Organization.objects.create(
            user=cls.active_owner, name="Active Search Organization", country="GH",
        )
        cls.inactive_owner = User.objects.create_user(
            username="privacy_inactive_owner", role="ORGANIZATION",
        )
        cls.inactive_org = Organization.objects.create(
            user=cls.inactive_owner, name="Inactive Search Organization",
            country="GH", status="INACTIVE",
        )
        cls.unlinked_owner = User.objects.create_user(
            username="privacy_unlinked_owner", role="ORGANIZATION",
        )

    def viewers(self):
        return (
            (self.ordinary, {self.public.pk}),
            (self.coach, {self.public.pk}),
            (self.scout, {self.public.pk}),
            (self.admin, {self.public.pk}),
            (self.active_owner, {self.public.pk, self.org_talent.pk}),
            (self.inactive_owner, {self.public.pk}),
            (self.unlinked_owner, {self.public.pk}),
            (self.private_user, {self.public.pk, self.private.pk}),
            (self.org_talent_user, {self.public.pk, self.org_talent.pk}),
        )

    def assert_search_results(self, response, expected):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.context["talents"].values_list("pk", flat=True)), expected,
        )
        for profile in (self.public, self.org_talent, self.private):
            if profile.pk not in expected:
                self.assertNotContains(response, profile.headline)

    def test_anonymous_search_only_selects_public_profiles(self):
        response = self.client.get("/search/")
        self.assert_search_results(response, {self.public.pk})
        for user in (self.org_talent_user, self.private_user):
            response = self.client.get("/search/", {"search": f"@{user.username}"})
            self.assertEqual(response.context["user_results"], [])

    def test_web_search_visibility_matches_api_for_each_viewer(self):
        api = APIClient()
        for viewer, expected in self.viewers():
            with self.subTest(viewer=viewer.username):
                self.client.force_login(viewer)
                api.force_authenticate(viewer)
                response = api.get("/api/talents/")
                self.assertEqual(response.status_code, 200)
                self.assertEqual({item["id"] for item in response.data}, expected)
                for path in ("/search/", "/talents/search/"):
                    self.assert_search_results(self.client.get(path), expected)

    def test_organization_search_does_not_grant_organization_visibility_by_its_url(self):
        for viewer, expected in self.viewers():
            with self.subTest(viewer=viewer.username):
                self.client.force_login(viewer)
                response = self.client.get("/organizations/talent-search/")
                if viewer != self.active_owner:
                    self.assertEqual(response.status_code, 403)
                    self.assertNotContains(response, self.org_talent.headline, status_code=403)
                else:
                    self.assert_search_results(response, expected)

    def test_exact_username_search_does_not_leak_hidden_profile_metadata(self):
        for viewer, expected in self.viewers():
            self.client.force_login(viewer)
            for profile in (self.public, self.org_talent, self.private):
                with self.subTest(viewer=viewer.username, profile=profile.pk):
                    response = self.client.get(
                        "/search/", {"search": f"@{profile.user.username.upper()}"},
                    )
                    self.assertEqual(response.status_code, 200)
                    users = [item["user"].pk for item in response.context["user_results"]]
                    self.assertEqual(
                        users, [profile.user_id] if profile.pk in expected else [],
                    )
                    if profile.pk not in expected:
                        self.assertNotContains(response, profile.headline)

    def test_username_suggestions_follow_the_same_privacy_rules(self):
        for viewer, expected in self.viewers():
            self.client.force_login(viewer)
            for profile in (self.public, self.org_talent, self.private):
                with self.subTest(viewer=viewer.username, profile=profile.pk):
                    response = self.client.get(
                        "/search/username-suggestions/",
                        {"q": f"@{profile.user.username}"},
                    )
                    self.assertEqual(response.status_code, 200)
                    names = [item["username"] for item in response.json()["results"]]
                    self.assertEqual(
                        names, [profile.user.username] if profile.pk in expected else [],
                    )

    def test_keyword_search_cannot_find_hidden_profiles_by_biography(self):
        self.org_talent.biography = "restricted_organisation_biography"
        self.org_talent.save(update_fields=["biography"])
        self.private.biography = "restricted_private_biography"
        self.private.save(update_fields=["biography"])
        self.client.force_login(self.ordinary)
        for term in ("restricted_organisation_biography", "restricted_private_biography"):
            response = self.client.get("/search/", {"search": term})
            self.assert_search_results(response, set())
        response = self.client.get(
            "/organizations/talent-search/", {"q": "restricted_organisation_biography"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertNotContains(response, self.org_talent.headline, status_code=403)

    def test_query_parameters_cannot_grant_organization_access(self):
        self.client.force_login(self.ordinary)
        data = {
            "role": "ORGANIZATION", "visibility": "ORGANIZATIONS",
            "organization_id": self.active_org.pk,
        }
        for path in ("/search/", "/talents/search/", "/organizations/talent-search/"):
            with self.subTest(path=path):
                response = self.client.get(path, data)
                if path == "/organizations/talent-search/":
                    self.assertEqual(response.status_code, 403)
                    continue
                self.assertEqual(response.status_code, 200)
                ids = set(response.context["talents"].values_list("pk", flat=True))
                self.assertNotIn(self.org_talent.pk, ids)
                self.assertNotIn(self.private.pk, ids)

    def test_direct_profile_urls_match_api_and_do_not_record_denied_views(self):
        api = APIClient()
        for viewer, expected in self.viewers():
            self.client.force_login(viewer)
            api.force_authenticate(viewer)
            for profile in (self.public, self.org_talent, self.private):
                with self.subTest(viewer=viewer.username, profile=profile.pk):
                    count_before = TalentProfileView.objects.count()
                    expected_status = 200 if profile.pk in expected else 404
                    response = self.client.get(
                        reverse("talent_profile", args=[profile.pk]),
                    )
                    self.assertEqual(response.status_code, expected_status)
                    self.assertEqual(
                        api.get(f"/api/talents/{profile.pk}/").status_code, expected_status,
                    )
                    if expected_status == 404:
                        self.assertNotContains(response, profile.headline, status_code=404)
                        self.assertEqual(TalentProfileView.objects.count(), count_before)

    def test_existing_sessions_lose_privileged_search_access_after_suspension(self):
        self.client.force_login(self.active_owner)
        self.assert_search_results(
            self.client.get("/search/"), {self.public.pk, self.org_talent.pk},
        )
        # Retain a cached organisation object while changing the database status.
        cached_org = self.active_owner.organization_profile
        for status in ("INACTIVE", "MERGED", "CLOSED"):
            with self.subTest(status=status):
                Organization.objects.filter(pk=self.active_org.pk).update(status=status)
                self.assertEqual(cached_org.status, "ACTIVE")
                self.assert_search_results(self.client.get("/search/"), {self.public.pk})
                self.assertEqual(
                    self.client.get(
                        reverse("talent_profile", args=[self.org_talent.pk]),
                    ).status_code, 404,
                )
                response = self.client.get(
                    "/search/username-suggestions/", {"q": self.org_talent_user.username},
                )
                self.assertEqual(response.json()["results"], [])
                self.assertEqual(
                    self.client.get("/organizations/talent-search/").status_code, 403,
                )

    def test_reactivation_restores_organization_only_access_but_not_private_access(self):
        self.client.force_login(self.inactive_owner)
        self.assert_search_results(self.client.get("/search/"), {self.public.pk})
        Organization.objects.filter(pk=self.inactive_org.pk).update(status="ACTIVE")
        self.assert_search_results(
            self.client.get("/search/"), {self.public.pk, self.org_talent.pk},
        )
        self.assertEqual(
            self.client.get(reverse("talent_profile", args=[self.private.pk])).status_code,
            404,
        )

    def test_owner_can_find_own_private_profile_in_personal_search(self):
        self.client.force_login(self.private_user)
        response = self.client.get("/search/", {"search": self.private.headline})
        self.assert_search_results(response, {self.private.pk})
        response = self.client.get(
            "/talents/search/", {"q": self.private.headline},
        )
        self.assert_search_results(response, {self.private.pk})

    def test_suspension_does_not_remove_an_organizations_own_profile_access(self):
        own_profile = TalentProfile.objects.create(
            user=self.inactive_owner, profile_visibility="PRIVATE",
            availability_status="AVAILABLE",
        )
        self.client.force_login(self.inactive_owner)
        self.assert_search_results(
            self.client.get("/search/"), {self.public.pk, own_profile.pk},
        )
        self.assertEqual(
            self.client.get(reverse("talent_profile", args=[own_profile.pk])).status_code,
            200,
        )

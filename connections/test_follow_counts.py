from importlib import import_module

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from connections.models import Follow, OrganizationFollow
from organizations.models import Organization
from talents.models import TalentProfile


User = get_user_model()


class FollowCountApiTests(APITestCase):
    def setUp(self):
        self.viewer = User.objects.create_user(
            username="follow_count_viewer", password="test-password", role="ATHLETE",
        )
        self.target = User.objects.create_user(
            username="follow_count_target", password="test-password", role="ATHLETE",
        )
        self.other = User.objects.create_user(
            username="follow_count_other", password="test-password", role="ATHLETE",
        )
        self.talent = TalentProfile.objects.create(user=self.target, followers_count=71)
        self.client.force_authenticate(user=self.viewer)

    def test_user_counts_and_api_response_use_follow_rows(self):
        response = self.client.post(
            "/api/follows/create/", {"user_id": self.target.pk}, format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["followers_count"], 1)
        self.assertEqual(response.data["following_count"], 0)
        self.assertEqual(TalentProfile.objects.get(pk=self.talent.pk).followers_count, 72)

        Follow.objects.create(follower=self.target, following=self.other)
        profile_response = self.client.get(f"/api/talents/{self.talent.pk}/")
        self.assertEqual(profile_response.status_code, 200)
        self.assertEqual(profile_response.data["followers_count"], 1)
        self.assertEqual(profile_response.data["following_count"], 1)

        repeated = self.client.post(
            "/api/follows/create/", {"user_id": self.target.pk}, format="json",
        )
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.data["followers_count"], 1)
        self.assertEqual(Follow.objects.filter(follower=self.viewer, following=self.target).count(), 1)

        removed = self.client.delete(f"/api/follows/{self.target.pk}/remove/")
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(removed.data["followers_count"], 0)
        self.assertEqual(TalentProfile.objects.get(pk=self.talent.pk).followers_count, 71)

    def test_following_counts_are_directional(self):
        Follow.objects.create(follower=self.viewer, following=self.target)
        Follow.objects.create(follower=self.viewer, following=self.other)
        response = self.client.get(f"/api/talents/{self.talent.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["followers_count"], 1)
        self.assertEqual(response.data["following_count"], 0)


class OrganizationFollowCountApiTests(APITestCase):
    def setUp(self):
        self.viewer = User.objects.create_user(
            username="organization_follow_viewer", password="test-password", role="ATHLETE",
        )
        self.other = User.objects.create_user(
            username="organization_follow_other", password="test-password", role="ATHLETE",
        )
        owner = User.objects.create_user(
            username="organization_follow_owner", password="test-password", role="ORGANIZATION",
        )
        self.organization = Organization.objects.create(user=owner, name="Follow Count Club")
        self.client.force_authenticate(user=self.viewer)

    def test_organization_api_counts_canonical_follows_and_is_idempotent(self):
        OrganizationFollow.objects.create(user=self.viewer, organization=self.organization)
        # The legacy M2M relation is still present for old integrations. Its rows
        # must not be counted a second time as active organization follows.
        self.organization.followers.add(self.other)

        detail = self.client.get(f"/api/organizations/{self.organization.pk}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["followers_count"], 1)

        repeated = self.client.post(f"/api/organizations/{self.organization.pk}/follow/")
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.data["followers_count"], 1)
        self.assertEqual(
            OrganizationFollow.objects.filter(organization=self.organization).count(), 1,
        )

        removed = self.client.delete(f"/api/organizations/{self.organization.pk}/unfollow/")
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(removed.data["followers_count"], 0)


class FollowCountWebTests(TestCase):
    def setUp(self):
        self.viewer = User.objects.create_user(
            username="web_follow_viewer", password="test-password", role="ATHLETE",
        )
        self.target = User.objects.create_user(
            username="web_follow_target", password="test-password", role="ATHLETE",
        )
        self.talent = TalentProfile.objects.create(
            user=self.target, is_role_model=True, followers_count=91,
        )
        self.client.force_login(self.viewer)

    def test_talent_profile_and_role_model_show_live_counts(self):
        Follow.objects.create(follower=self.viewer, following=self.target)
        response = self.client.get(reverse("talent_profile", args=[self.talent.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1</strong> followers")
        self.assertContains(response, "0</strong> following")

        role_models = self.client.get(reverse("role_models"))
        self.assertEqual(role_models.status_code, 200)
        self.assertContains(role_models, "1")

    def test_organization_profile_renders_one_canonical_count(self):
        owner = User.objects.create_user(
            username="web_follow_org_owner", password="test-password", role="ORGANIZATION",
        )
        organization = Organization.objects.create(user=owner, name="Web Follow Club")
        OrganizationFollow.objects.create(user=self.viewer, organization=organization)
        response = self.client.get(reverse("organization_profile", args=[organization.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["followers"], 1)
        self.assertContains(response, "Followers:")
        self.assertEqual(response.content.count(b"Followers:"), 1)


class FollowCountMigrationTests(TransactionTestCase):
    def test_legacy_organization_follows_and_cached_talent_counts_are_reconciled(self):
        viewer = User.objects.create_user(username="legacy_follow_viewer", role="ATHLETE")
        target = User.objects.create_user(username="legacy_follow_target", role="ATHLETE")
        owner = User.objects.create_user(username="legacy_follow_owner", role="ORGANIZATION")
        organization = Organization.objects.create(user=owner, name="Legacy Follow Club")
        talent = TalentProfile.objects.create(user=target, followers_count=19)
        organization.followers.add(viewer)
        Follow.objects.create(follower=viewer, following=target)

        state = MigrationExecutor(connection).loader.project_state([
            ("connections", "0006_reconcile_follow_counts"),
        ])
        reconcile_follow_data = import_module(
            "connections.migrations.0006_reconcile_follow_counts",
        ).reconcile_follow_data
        reconcile_follow_data(state.apps, type("SchemaEditor", (), {"connection": connection})())

        self.assertTrue(OrganizationFollow.objects.filter(
            user=viewer, organization=organization,
        ).exists())
        talent.refresh_from_db()
        self.assertEqual(talent.followers_count, 1)

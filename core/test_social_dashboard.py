from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserBlock
from connections.models import Connection, Follow
from domains.models import TalentDomain
from feed.models import Post, PostLike, SavedPost, SharedPost
from talents.models import TalentProfile


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class SocialDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.domain = TalentDomain.objects.create(name="Illustration")
        cls.viewer = cls.person("social_viewer")
        cls.friend = cls.person("social_friend")
        cls.peer = cls.person("social_peer")
        Follow.objects.create(follower=cls.viewer, following=cls.friend)
        cls.image = Post.objects.create(author=cls.friend, talent=cls.friend.talent_profile,
                                       caption="Visible illustration", image="feed/images/example.jpg")
        cls.video = Post.objects.create(author=cls.peer, talent=cls.peer.talent_profile,
                                       caption="Visible video practice", video="feed/videos/example.mp4")
        cls.followers = Post.objects.create(author=cls.friend, caption="Follower moment", visibility="FOLLOWERS")
        cls.private = Post.objects.create(author=cls.friend, caption="SECRET private caption", visibility="PRIVATE",
                                         video="feed/videos/private.mp4")

    @classmethod
    def person(cls, name, **kwargs):
        user = get_user_model().objects.create_user(username=name, **kwargs)
        profile = TalentProfile.objects.create(user=user, talent_category="ARTS", talent_area="Illustration")
        profile.domains.add(cls.domain)
        return user

    def setUp(self):
        self.client.force_login(self.viewer)

    def post_ids(self, response):
        return {item["object"].pk for item in response.context["feed_items"] if item["type"] == "POST"}

    def test_stories_and_reels_keep_the_same_audience_in_both_pipelines(self):
        for enabled in (False, True):
            with self.subTest(unified=enabled), override_settings(UNIFIED_RECOMMENDATIONS_ENABLED=enabled):
                response = self.client.get(reverse("home_feed"))
                self.assertEqual(response.status_code, 200)
                self.assertIn(self.image.pk, self.post_ids(response))
                self.assertIn(self.followers.pk, self.post_ids(response))
                self.assertNotIn(self.private.pk, self.post_ids(response))
                stories = response.context["story_posts"]
                self.assertEqual(len({post.author_id for post in stories}), len(stories))
                self.assertNotIn(self.private.pk, {post.pk for post in stories})
                self.assertNotContains(response, "SECRET private caption")
                reels = self.client.get(reverse("home_feed"), {"view": "reels"})
                self.assertIn(self.video.pk, self.post_ids(reels))
                self.assertNotIn(self.image.pk, self.post_ids(reels))
                self.assertNotContains(reels, "SECRET private caption")

    def test_following_filters_without_losing_the_full_feed(self):
        response = self.client.get(reverse("home_feed"), {"view": "following"})
        self.assertIn(self.image.pk, self.post_ids(response))
        self.assertIn(self.followers.pk, self.post_ids(response))
        self.assertNotIn(self.video.pk, self.post_ids(response))
        self.assertIn(self.video.pk, self.post_ids(self.client.get(reverse("home_feed"))))

    def test_stories_expire_from_the_strip_but_posts_remain_in_feed(self):
        old = Post.objects.create(author=self.viewer, caption="Older post")
        Post.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(hours=25))
        response = self.client.get(reverse("home_feed"))
        self.assertIn(old.pk, self.post_ids(response))
        self.assertNotIn(old.pk, {post.pk for post in response.context["story_posts"]})

    @override_settings(UNIFIED_RECOMMENDATIONS_ENABLED=True)
    def test_stories_do_not_resurface_items_omitted_by_the_ranked_feed(self):
        def rank_subset(user, entries):
            return [{"feed_entry": entry, "score": 10, "matched_topics": [], "explanation": "Test subset"}
                    for entry in entries if entry["type"] == "POST" and entry["object"].pk == self.image.pk]

        with patch("core.views.UnifiedRecommendationService") as service:
            service.return_value.rank_feed_items.side_effect = rank_subset
            response = self.client.get(reverse("home_feed"))
        self.assertEqual(self.post_ids(response), {self.image.pk})
        self.assertEqual({post.pk for post in response.context["story_posts"]}, {self.image.pk})

    def test_blocked_accounts_never_appear_in_stories_feed_or_recommendations(self):
        UserBlock.objects.create(user=self.friend, blocked_user=self.viewer)
        response = self.client.get(reverse("home_feed"))
        self.assertNotIn(self.image.pk, self.post_ids(response))
        self.assertNotIn(self.friend.pk, {post.author_id for post in response.context["story_posts"]})
        self.assertNotIn(self.friend.pk, {profile.user_id for profile in response.context["recommended_talents"]})

    def test_a_repost_does_not_reveal_an_original_that_became_private(self):
        SharedPost.objects.create(user=self.viewer, post=self.private)
        response = self.client.get(reverse("home_feed"))
        self.assertFalse(any(item["type"] == "SHARE" and item["object"].post_id == self.private.pk
                             for item in response.context["feed_items"]))
        self.assertNotContains(response, "SECRET private caption")

    def test_private_talent_profiles_are_not_suggested(self):
        profile = self.peer.talent_profile
        profile.profile_visibility = "PRIVATE"
        profile.save(update_fields=["profile_visibility"])
        response = self.client.get(reverse("home_feed"))
        self.assertNotIn(profile.pk, {item.pk for item in response.context["recommended_talents"]})

    def test_liked_and_saved_state_is_preserved_for_repost_only_posts(self):
        outsider = get_user_model().objects.create_user(username="outside_ecosystem")
        original = Post.objects.create(author=outsider, caption="A public repost outside the ecosystem")
        shared = SharedPost.objects.create(user=self.friend, post=original)
        PostLike.objects.create(user=self.viewer, post=original)
        SavedPost.objects.create(user=self.viewer, post=original)
        response = self.client.get(reverse("home_feed"))
        self.assertTrue(any(item["type"] == "SHARE" and item["object"].pk == shared.pk
                            for item in response.context["feed_items"]))
        self.assertIn(original.pk, response.context["liked_post_ids"])
        self.assertIn(original.pk, response.context["saved_post_ids"])

    def test_dashboard_keeps_role_routing_and_account_tools(self):
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("talent_dashboard"),
                             fetch_redirect_response=False)
        response = self.client.get(reverse("talent_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "talents/dashboard.html")
        self.assertTemplateNotUsed(response, "core/home_feed.html")
        self.assertNotIn("feed_items", response.context)
        self.assertNotContains(response, "Visible illustration")
        self.assertNotContains(response, 'aria-label="Feed views"')
        for label in ("Profile strength", "Recent applications", "Invitations", "Recent conversations", "Notifications"):
            self.assertContains(response, label)
        self.assertNotContains(response, f'action="{reverse("like_post", args=[self.image.pk])}"')
        self.assertContains(response, reverse("messaging:conversation_list"))

    def test_post_actions_still_require_csrf_and_keep_django_fallbacks(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.viewer)
        url = reverse("like_post", args=[self.image.pk])
        self.assertEqual(browser.post(url).status_code, 403)
        self.assertEqual(browser.get(url).status_code, 405)
        browser.get(reverse("home_feed"))
        response = browser.post(url, {"csrfmiddlewaretoken": browser.cookies["csrftoken"].value})
        self.assertRedirects(response, reverse("home_feed"), fetch_redirect_response=False)

    def test_anonymous_access_requires_login_and_unknown_view_is_safe(self):
        self.assertEqual(Client().get(reverse("home_feed")).status_code, 302)
        response = self.client.get(reverse("home_feed"), {"view": "<script>"})
        self.assertEqual(response.context["feed_view"], "for-you")
        self.assertNotContains(response, "<script></script>")

    def test_home_and_dashboard_have_independent_routes_templates_and_content(self):
        from django.urls import resolve
        from core.views import home_feed
        from talents.views import talent_dashboard

        self.assertNotEqual(reverse("home_feed"), reverse("talent_dashboard"))
        self.assertIs(resolve(reverse("home_feed")).func, home_feed)
        self.assertIs(resolve(reverse("talent_dashboard")).func, talent_dashboard)
        home = self.client.get(reverse("home_feed"))
        self.assertTemplateUsed(home, "core/home_feed.html")
        self.assertTemplateNotUsed(home, "talents/dashboard.html")
        self.assertContains(home, "Visible illustration")
        self.assertContains(home, 'aria-label="Feed views"')
        self.assertNotContains(home, 'id="dashboard-progress-title"')
        self.assertNotIn("total_applications", home.context)
        for view in ("following", "reels"):
            dashboard = self.client.get(reverse("talent_dashboard"), {"view": view})
            self.assertContains(dashboard, "Profile strength")
            self.assertNotIn("feed_items", dashboard.context)
        for name in ("dashboard", "talent_dashboard", "home_feed"):
            self.assertEqual(Client().get(reverse(name)).status_code, 302)
        for response in (home, dashboard):
            self.assertContains(response, f'href="{reverse("dashboard")}"')
            self.assertContains(response, f'href="{reverse("home_feed")}"')
            self.assertContains(response, f'href="{reverse("home_feed")}?view=reels"')

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from feed.models import Post
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
class HomeFeedTests(TestCase):
	def setUp(self):
		self.user = get_user_model().objects.create_user(
			username="feed_viewer",
			password="TestPass123!",
		)
		self.client.force_login(self.user)

	def test_home_feed_loads_without_an_unbound_events_error(self):
		response = self.client.get(reverse("home_feed"))

		self.assertEqual(response.status_code, 200)

	def test_authenticated_home_visit_shows_loader_before_feed(self):
		response = self.client.get(reverse("home"))

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "loading.html")
		self.assertEqual(response.context["redirect_url"], reverse("home_feed"))
		self.assertContains(response, "Loading your home feed")
		self.assertContains(response, 'http-equiv="refresh"')

	def test_talent_post_card_shows_talent_category_instead_of_account_role(self):
		talent = TalentProfile.objects.create(
			user=self.user,
			talent_category="ARTS",
		)
		Post.objects.create(
			author=self.user,
			talent=talent,
			caption="My latest artwork",
		)

		response = self.client.get(reverse("home_feed"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Arts")
		self.assertContains(response, "save-button")
		self.assertContains(response, "share-form")
		self.assertNotContains(response, "window.location.href")


class PublicHomeTests(TestCase):
	def test_anonymous_home_visit_still_shows_landing_page(self):
		response = self.client.get(reverse("home"))

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "loading.html")
		self.assertContains(response, "Where Talent Meets Opportunities")

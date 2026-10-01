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

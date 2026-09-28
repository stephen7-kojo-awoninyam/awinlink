from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


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

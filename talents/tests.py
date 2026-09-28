from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import TalentProfile


class TalentDashboardTests(TestCase):
	def setUp(self):
		self.user = get_user_model().objects.create_user(
			username="dashboard_talent",
			password="TestPass123!",
			first_name="Amina",
		)
		self.profile = TalentProfile.objects.create(
			user=self.user,
			talent_category="SPORTS",
			talent_area="Basketball",
			headline="Point guard",
			biography="Regional basketball player.",
			country="Ghana",
			city="Accra",
		)
		self.client.force_login(self.user)

	def test_dashboard_renders_saved_talent_information(self):
		dashboard_entry = self.client.get(reverse("dashboard"))
		self.assertRedirects(
			dashboard_entry,
			reverse("talent_dashboard"),
			fetch_redirect_response=False,
		)

		response = self.client.get(dashboard_entry.url)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Point guard")
		self.assertContains(response, "Ghana")
		self.assertContains(response, "Accra")
		self.assertContains(response, "Regional basketball player.")

from io import BytesIO
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

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


class TalentProfileImageTests(TestCase):
	def setUp(self):
		self.user = get_user_model().objects.create_user(
			username="photo_talent",
			password="TestPass123!",
		)
		self.profile = TalentProfile.objects.create(user=self.user)
		self.client.force_login(self.user)

	@override_settings(DEBUG=False)
	def test_uploaded_profile_and_cover_photos_are_served_in_production(self):
		image_buffer = BytesIO()
		Image.new("RGB", (2, 2), color=(30, 100, 210)).save(
			image_buffer,
			format="PNG",
		)
		image_content = image_buffer.getvalue()
		profile_filename = f"profile-{uuid4().hex}.png"
		cover_filename = f"cover-{uuid4().hex}.png"
		file_names = []
		self.addCleanup(lambda: [default_storage.delete(name) for name in file_names])

		response = self.client.post(
			reverse("edit_profile"),
			{
				"talent_category": "SPORTS",
				"talent_area": "Basketball",
				"headline": "Point guard",
				"biography": "A profile photo test.",
				"country": "Ghana",
				"city": "Accra",
				"experience_level": "BEGINNER",
				"preferred_work_type": "REMOTE",
				"profile_photo": SimpleUploadedFile(
					profile_filename,
					image_content,
					content_type="image/png",
				),
				"cover_photo": SimpleUploadedFile(
					cover_filename,
					image_content,
					content_type="image/png",
				),
			},
		)

		self.assertRedirects(
			response,
			reverse("talent_dashboard"),
			fetch_redirect_response=False,
		)
		self.profile.refresh_from_db()
		self.assertTrue(self.profile.profile_photo)
		self.assertTrue(self.profile.cover_photo)
		file_names.extend((self.profile.profile_photo.name, self.profile.cover_photo.name))

		for image in (self.profile.profile_photo, self.profile.cover_photo):
			image_response = self.client.get(image.url)
			self.assertEqual(image_response.status_code, 200)
			self.assertEqual(b"".join(image_response.streaming_content), image_content)
			image_response.close()

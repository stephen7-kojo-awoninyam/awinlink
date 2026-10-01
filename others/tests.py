from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from others.models import OtherTalentProfile
from talents.models import TalentProfile


User = get_user_model()


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
class OtherTalentProfileSetupTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			username="other_talent_web",
			password="test-password",
			role="ATHLETE",
		)
		self.talent = TalentProfile.objects.create(
			user=self.user,
			talent_category="OTHERS",
		)

	def test_canonical_and_legacy_setup_routes_share_the_same_page(self):
		self.client.force_login(self.user)

		canonical_response = self.client.get("/others/profile-setup/")
		legacy_response = self.client.get("/talents/other-profile-setup/")

		self.assertEqual(canonical_response.status_code, 200)
		self.assertEqual(legacy_response.status_code, 200)
		self.assertTemplateUsed(canonical_response, "others/profile_setup.html")
		self.assertTemplateUsed(legacy_response, "others/profile_setup.html")

	def test_setup_form_saves_profile_for_signed_in_talent(self):
		self.client.force_login(self.user)

		response = self.client.post(
			"/others/profile-setup/",
			{
				"specialization": "Consultant",
				"description": "Supports local businesses.",
				"years_of_experience": "3",
			},
		)

		self.assertRedirects(response, "/talents/dashboard/")
		profile = OtherTalentProfile.objects.get(talent=self.talent)
		self.assertEqual(profile.specialization, "Consultant")
		self.assertEqual(profile.years_of_experience, 3)

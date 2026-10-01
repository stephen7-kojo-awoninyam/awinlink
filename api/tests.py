from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from applications.models import Application
from domains.models import TalentDomain
from opportunities.models import Opportunity
from organizations.models import Organization
from talents.models import TalentProfile
from others.models import OtherTalentProfile


User = get_user_model()


class ApplicationDetailPermissionTests(APITestCase):
	def setUp(self):
		self.applicant = User.objects.create_user(
			username="applicant",
			password="TestPass123!",
			role="ATHLETE",
		)
		self.organization_user = User.objects.create_user(
			username="hiring_org",
			password="TestPass123!",
			role="ORGANIZATION",
		)
		self.outsider = User.objects.create_user(
			username="outsider",
			password="TestPass123!",
			role="ATHLETE",
		)

		talent = TalentProfile.objects.create(user=self.applicant)
		organization = Organization.objects.create(
			user=self.organization_user,
			name="Hiring Organization",
			country="Nigeria",
		)
		domain = TalentDomain.objects.create(name="Sports")
		opportunity = Opportunity.objects.create(
			organization=organization,
			domain=domain,
			title="Athlete role",
			description="Open position",
		)
		self.application = Application.objects.create(
			talent=talent,
			opportunity=opportunity,
			message="Please consider my application.",
		)
		self.private_talent = TalentProfile.objects.create(
			user=self.outsider,
			profile_visibility="PRIVATE",
		)
		organization_only_user = User.objects.create_user(
			username="organization_only_talent",
			password="TestPass123!",
			role="ATHLETE",
		)
		self.organization_only_talent = TalentProfile.objects.create(
			user=organization_only_user,
			profile_visibility="ORGANIZATIONS",
		)
		self.url = f"/api/applications/{self.application.id}/"

	def test_applicant_can_view_their_application(self):
		self.client.force_authenticate(user=self.applicant)

		response = self.client.get(self.url)

		self.assertEqual(response.status_code, 200)

	def test_hiring_organization_can_view_application(self):
		self.client.force_authenticate(user=self.organization_user)

		response = self.client.get(self.url)

		self.assertEqual(response.status_code, 200)

	def test_unrelated_user_cannot_view_application(self):
		self.client.force_authenticate(user=self.outsider)

		response = self.client.get(self.url)

		self.assertEqual(response.status_code, 403)

	def test_talent_list_hides_profiles_the_user_cannot_view(self):
		self.client.force_authenticate(user=self.applicant)

		response = self.client.get("/api/talents/")

		self.assertEqual(response.status_code, 200)
		profile_ids = {profile["id"] for profile in response.data}
		self.assertNotIn(self.private_talent.id, profile_ids)
		self.assertNotIn(self.organization_only_talent.id, profile_ids)

	def test_organization_can_view_organization_only_talent(self):
		self.client.force_authenticate(user=self.organization_user)

		response = self.client.get(
			f"/api/talents/{self.organization_only_talent.id}/"
		)

		self.assertEqual(response.status_code, 200)

	def test_private_talent_is_visible_only_to_the_owner(self):
		self.client.force_authenticate(user=self.applicant)

		response = self.client.get(f"/api/talents/{self.private_talent.id}/")

		self.assertEqual(response.status_code, 404)

		self.client.force_authenticate(user=self.outsider)
		response = self.client.get(f"/api/talents/{self.private_talent.id}/")

		self.assertEqual(response.status_code, 200)

	def test_follow_create_route_accepts_user_id_in_request_body(self):
		self.client.force_authenticate(user=self.applicant)

		response = self.client.post(
			"/api/follows/create/",
			{"user_id": self.outsider.id},
			format="json",
		)

		self.assertEqual(response.status_code, 201)


class OtherTalentProfileApiTests(APITestCase):
	def setUp(self):
		self.owner = User.objects.create_user(
			username="other_talent",
			password="test-password",
			role="ATHLETE",
		)
		self.talent = TalentProfile.objects.create(
			user=self.owner,
			talent_category="OTHERS",
		)
		self.url = "/api/talents/me/others/"

	def test_owner_can_create_read_and_update_other_profile(self):
		self.client.force_authenticate(user=self.owner)

		create_response = self.client.post(
			self.url,
			{
				"specialization": "Entrepreneur",
				"years_of_experience": 4,
			},
			format="json",
		)

		self.assertEqual(create_response.status_code, 201)
		self.assertEqual(
			create_response.data["specialization"],
			"Entrepreneur",
		)
		self.assertEqual(
			OtherTalentProfile.objects.get(talent=self.talent).years_of_experience,
			4,
		)

		read_response = self.client.get(self.url)
		self.assertEqual(read_response.status_code, 200)

		update_response = self.client.patch(
			self.url,
			{"description": "Builds community businesses."},
			format="json",
		)
		self.assertEqual(update_response.status_code, 200)
		self.assertEqual(
			update_response.data["description"],
			"Builds community businesses.",
		)

	def test_other_profile_is_included_in_visible_talent_detail(self):
		OtherTalentProfile.objects.create(
			talent=self.talent,
			specialization="Consultant",
		)
		self.client.force_authenticate(user=self.owner)

		response = self.client.get(f"/api/talents/{self.talent.id}/")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(
			response.data["other_profile"]["specialization"],
			"Consultant",
		)

	def test_talent_without_other_profile_serializes_null(self):
		self.client.force_authenticate(user=self.owner)

		response = self.client.get(f"/api/talents/{self.talent.id}/")

		self.assertEqual(response.status_code, 200)
		self.assertIsNone(response.data["other_profile"])

	def test_api_cannot_read_or_update_another_talents_profile(self):
		OtherTalentProfile.objects.create(
			talent=self.talent,
			specialization="Private",
		)
		other_user = User.objects.create_user(
			username="another_talent",
			password="test-password",
			role="ATHLETE",
		)
		TalentProfile.objects.create(
			user=other_user,
			talent_category="OTHERS",
		)
		self.client.force_authenticate(user=other_user)

		read_response = self.client.get(self.url)
		update_response = self.client.patch(
			self.url,
			{"specialization": "Unauthorized change"},
			format="json",
		)

		self.assertEqual(read_response.status_code, 404)
		self.assertEqual(update_response.status_code, 404)
		self.assertEqual(
			self.talent.other_profile.specialization,
			"Private",
		)

	def test_endpoint_rejects_non_others_categories(self):
		self.talent.talent_category = "SPORTS"
		self.talent.save(update_fields=["talent_category"])
		self.client.force_authenticate(user=self.owner)

		response = self.client.get(self.url)

		self.assertEqual(response.status_code, 400)

	def test_create_rejects_invalid_urls(self):
		self.client.force_authenticate(user=self.owner)

		response = self.client.post(
			self.url,
			{"website": "not-a-url"},
			format="json",
		)

		self.assertEqual(response.status_code, 400)
		self.assertFalse(
			OtherTalentProfile.objects.filter(talent=self.talent).exists()
		)

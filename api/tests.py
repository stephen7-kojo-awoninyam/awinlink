from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from applications.models import Application
from domains.models import TalentDomain
from opportunities.models import Opportunity
from organizations.models import Organization
from talents.models import TalentProfile


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

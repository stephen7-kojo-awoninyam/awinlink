from io import BytesIO
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from connections.models import OrganizationFollow
from domains.models import TalentDomain
from invitations.models import Invitation
from opportunities.models import Opportunity
from recruitment.models import RecruitmentStage

from .forms import OrganizationForm
from .models import Organization, OrganizationCategory


class OrganizationTests(TestCase):
	def setUp(self):
		user_model = get_user_model()
		self.org_user = user_model.objects.create_user(
			username="org_owner",
			password="TestPass123!",
			role="ORGANIZATION",
		)
		self.viewer = user_model.objects.create_user(
			username="org_viewer",
			password="TestPass123!",
		)
		self.talent_user = user_model.objects.create_user(
			username="org_talent",
			password="TestPass123!",
		)
		self.organization = Organization.objects.create(
			user=self.org_user,
			name="North Star Club",
			country="Ghana",
			city="Accra",
		)
		self.domain = TalentDomain.objects.create(name="Football")
		self.opportunity = Opportunity.objects.create(
			organization=self.organization,
			title="Youth Team Trial",
			description="Open trial for young players.",
			domain=self.domain,
		)

	def test_organization_directory_loads_and_filters_inactive_records(self):
		inactive = Organization.objects.create(
			name="Closed Academy",
			country="Ghana",
			status="CLOSED",
		)

		response = self.client.get(reverse("organization_directory"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, self.organization.name)
		self.assertNotContains(response, inactive.name)

	def test_organization_profile_shows_current_follow_state(self):
		self.client.force_login(self.viewer)
		OrganizationFollow.objects.create(
			user=self.viewer,
			organization=self.organization,
		)

		response = self.client.get(
			reverse("organization_profile", args=[self.organization.id])
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Following")
		self.assertNotContains(response, "href=\"/organizations/profile/")

	def test_follow_and_unfollow_are_post_only_and_idempotent(self):
		self.client.force_login(self.viewer)
		follow_url = reverse("follow_organization", args=[self.organization.id])
		unfollow_url = reverse("unfollow_organization", args=[self.organization.id])

		self.assertEqual(self.client.get(follow_url).status_code, 405)

		response = self.client.post(follow_url)
		self.assertEqual(response.status_code, 302)
		self.assertTrue(
			OrganizationFollow.objects.filter(
				user=self.viewer,
				organization=self.organization,
			).exists()
		)

		self.client.post(follow_url)
		self.assertEqual(
			OrganizationFollow.objects.filter(
				user=self.viewer,
				organization=self.organization,
			).count(),
			1,
		)

		self.assertEqual(self.client.get(unfollow_url).status_code, 405)
		self.client.post(unfollow_url)
		self.assertFalse(
			OrganizationFollow.objects.filter(
				user=self.viewer,
				organization=self.organization,
			).exists()
		)

	def test_invite_page_and_submission_create_invitation_and_pipeline_stage(self):
		self.client.force_login(self.org_user)
		talent = __import__("talents.models", fromlist=["TalentProfile"]).TalentProfile.objects.create(
			user=self.talent_user,
		)
		invite_url = reverse(
			"invite_talent",
			args=[talent.id, self.opportunity.id],
		)

		get_response = self.client.get(invite_url)
		self.assertEqual(get_response.status_code, 200)
		self.assertContains(get_response, self.opportunity.title)

		response = self.client.post(invite_url, {"message": "We would like to meet."})

		self.assertRedirects(
			response,
			reverse("organization_dashboard"),
			fetch_redirect_response=False,
		)
		self.assertTrue(
			Invitation.objects.filter(
				organization=self.organization,
				talent=talent,
				opportunity=self.opportunity,
				message="We would like to meet.",
			).exists()
		)
		self.assertEqual(
			RecruitmentStage.objects.get(
				organization=self.organization,
				talent=talent,
				opportunity=self.opportunity,
			).stage,
			"INVITED",
		)

	def test_cover_photo_is_editable(self):
		self.assertIn("cover_photo", OrganizationForm().fields)

	@override_settings(DEBUG=False)
	def test_public_organization_logo_media_is_served_in_production(self):
		image_buffer = BytesIO()
		Image.new("RGB", (2, 2), color=(35, 110, 80)).save(
			image_buffer,
			format="PNG",
		)
		image_bytes = image_buffer.getvalue()
		filename = f"organizations/logos/test-{uuid4().hex}.png"
		saved_name = default_storage.save(filename, ContentFile(image_bytes))
		self.addCleanup(default_storage.delete, saved_name)

		response = self.client.get(f"/media/{saved_name}")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(b"".join(response.streaming_content), image_bytes)
		response.close()

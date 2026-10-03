from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from events.models import Event, EventCategory
from feed.models import Post
from connections.models import Connection
from coaches.models import CoachProfile
from organizations.models import (
	Organization,
	OrganizationCategory,
	OrganizationDomain,
)
from scouts.models import ScoutProfile
from sports.models import Sport, SportsTalentProfile
from domains.models import TalentDomain
from learning.models import Course, LearningCategory
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
		self.assertContains(response, f'href="{reverse("logout")}"')
		self.assertContains(response, "Log out")

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

	def test_feed_is_discipline_scoped_but_keeps_cross_ecosystem_connections(self):
		basketball = Sport.objects.create(name="Basketball")
		tennis = Sport.objects.create(name="Tennis")

		self_talent = TalentProfile.objects.create(
			user=self.user,
			talent_category="SPORTS",
			talent_area="Basketball",
		)
		SportsTalentProfile.objects.create(
			talent=self_talent,
			sport=basketball,
		)

		basketball_user = get_user_model().objects.create_user(
			username="basketball_talent",
		)
		basketball_talent = TalentProfile.objects.create(
			user=basketball_user,
			talent_category="SPORTS",
			talent_area="Basketball",
		)
		SportsTalentProfile.objects.create(
			talent=basketball_talent,
			sport=basketball,
		)
		basketball_post = Post.objects.create(
			author=basketball_user,
			talent=basketball_talent,
			caption="Basketball ecosystem update",
		)

		tennis_user = get_user_model().objects.create_user(
			username="tennis_talent",
		)
		tennis_talent = TalentProfile.objects.create(
			user=tennis_user,
			talent_category="SPORTS",
			talent_area="Tennis",
		)
		SportsTalentProfile.objects.create(
			talent=tennis_talent,
			sport=tennis,
		)
		tennis_post = Post.objects.create(
			author=tennis_user,
			talent=tennis_talent,
			caption="Tennis ecosystem update",
		)

		technology_user = get_user_model().objects.create_user(
			username="technology_talent",
		)
		technology_talent = TalentProfile.objects.create(
			user=technology_user,
			talent_category="SCIENCE_TECHNOLOGY",
			talent_area="Artificial Intelligence",
		)
		technology_post = Post.objects.create(
			author=technology_user,
			talent=technology_talent,
			caption="Technology ecosystem update",
		)
		Connection.objects.create(
			sender=self.user,
			receiver=technology_user,
			status="ACCEPTED",
		)

		response = self.client.get(reverse("home_feed"))

		self.assertEqual(response.status_code, 200)
		visible_post_ids = {
			item["object"].pk
			for item in response.context["feed_items"]
			if item["type"] == "POST"
		}
		self.assertIn(basketball_post.pk, visible_post_ids)
		self.assertNotIn(tennis_post.pk, visible_post_ids)
		self.assertIn(technology_post.pk, visible_post_ids)

		coach_user = get_user_model().objects.create_user(
			username="basketball_coach",
			role="COACH",
		)
		CoachProfile.objects.create(
			user=coach_user,
			coach_category="SPORTS",
			sport=basketball,
			specialization="Basketball",
		)
		coach_post = Post.objects.create(
			author=coach_user,
			caption="Basketball coaching update",
		)

		scout_user = get_user_model().objects.create_user(
			username="basketball_scout",
			role="SCOUT",
		)
		ScoutProfile.objects.create(
			user=scout_user,
			scout_category="SPORTS",
			specialization="Basketball",
		)
		scout_post = Post.objects.create(
			author=scout_user,
			caption="Basketball scouting update",
		)

		category = OrganizationCategory.objects.create(name="Sports")
		domain = OrganizationDomain.objects.create(
			category=category,
			name="Basketball",
		)
		organization_user = get_user_model().objects.create_user(
			username="basketball_organization",
			role="ORGANIZATION",
		)
		organization = Organization.objects.create(
			user=organization_user,
			name="Basketball Academy",
			category=category,
			domain=domain,
			country="Ghana",
		)
		organization_post = Post.objects.create(
			author=organization_user,
			organization=organization,
			caption="Basketball organization update",
		)

		response = self.client.get(reverse("home_feed"))
		visible_post_ids = {
			item["object"].pk
			for item in response.context["feed_items"]
			if item["type"] == "POST"
		}
		self.assertIn(coach_post.pk, visible_post_ids)
		self.assertIn(scout_post.pk, visible_post_ids)
		self.assertIn(organization_post.pk, visible_post_ids)

		api_response = self.client.get("/api/feed/posts/")
		self.assertEqual(api_response.status_code, 200)
		api_post_ids = {post["id"] for post in api_response.json()}
		self.assertIn(basketball_post.pk, api_post_ids)
		self.assertNotIn(tennis_post.pk, api_post_ids)
		self.assertIn(technology_post.pk, api_post_ids)

	def test_feed_suggests_events_and_learning_for_the_talent_domain(self):
		domain = TalentDomain.objects.create(name="Basketball")
		TalentProfile.objects.create(
			user=self.user,
			talent_category="SPORTS",
			talent_area="Basketball",
		).domains.add(domain)

		organization = Organization.objects.create(
			user=get_user_model().objects.create_user(
				username="basketball_event_organizer",
				role="ORGANIZATION",
			),
			name="Basketball Events",
			country="Ghana",
		)
		relevant_event = Event.objects.create(
			organizer=organization,
			category=EventCategory.objects.create(
				name="Basketball",
				domain=domain,
			),
			title="Basketball skills clinic",
			slug="basketball-skills-clinic",
			description="A skills development clinic.",
			event_type="WORKSHOP",
			location="Accra",
			online=False,
			start_date=timezone.now() + timedelta(days=2),
			end_date=timezone.now() + timedelta(days=3),
			registration_deadline=timezone.now() + timedelta(days=1),
			status="PUBLISHED",
		)
		unrelated_event = Event.objects.create(
			organizer=organization,
			category=EventCategory.objects.create(name="Artificial Intelligence"),
			title="AI research meetup",
			slug="ai-research-meetup",
			description="A technology meetup.",
			event_type="CONFERENCE",
			location="Accra",
			online=True,
			start_date=timezone.now() + timedelta(days=2),
			end_date=timezone.now() + timedelta(days=3),
			registration_deadline=timezone.now() + timedelta(days=1),
			status="PUBLISHED",
		)

		relevant_course = Course.objects.create(
			creator=organization.user,
			category=LearningCategory.objects.create(name="Basketball"),
			title="Basketball Fundamentals",
			slug="basketball-fundamentals",
			description="Training for basketball players.",
			duration=60,
			status="APPROVED",
		)
		Course.objects.create(
			creator=organization.user,
			category=LearningCategory.objects.create(name="Artificial Intelligence"),
			title="AI Fundamentals",
			slug="ai-fundamentals",
			description="An introduction to AI.",
			duration=60,
			status="APPROVED",
		)

		response = self.client.get(reverse("home_feed"))

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context["events"], [relevant_event])
		self.assertNotIn(unrelated_event, response.context["events"])
		self.assertEqual(response.context["learning_content"], [relevant_course])


class PublicHomeTests(TestCase):
	def test_anonymous_home_visit_still_shows_landing_page(self):
		response = self.client.get(reverse("home"))

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "loading.html")
		self.assertContains(response, "Where Talent Meets Opportunities")

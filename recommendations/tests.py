from unittest.mock import patch
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from applications.models import Application
from domains.models import TalentDomain
from events.models import Event, EventCertificate
from learning.models import Course, Enrollment, LearningCategory
from opportunities.models import Opportunity, OpportunityRequirement
from organizations.models import Organization
from recommendations.services import RecommendationEngine
from skills.models import Skill, SkillCategory, SkillRelationship
from talents.models import TalentProfile


class TalentDiscoveryScoringTests(TestCase):
	def create_talent(self, username, **profile_fields):
		user = get_user_model().objects.create_user(username=username)
		return TalentProfile.objects.create(user=user, **profile_fields)

	@patch(
		"recommendations.services.ProfileStrengthService.calculate_strength",
		return_value=0,
	)
	def test_discovery_score_rewards_verified_and_role_model_profiles(
		self,
		_calculate_strength,
	):
		source = self.create_talent("source", talent_category="SPORTS")
		candidate = self.create_talent("candidate", talent_category="SPORTS")

		baseline = RecommendationEngine.score_talent_for_discovery(
			source,
			candidate,
		)
		candidate.verified = True
		candidate.is_role_model = True
		candidate.save(update_fields=["verified", "is_role_model"])

		improved = RecommendationEngine.score_talent_for_discovery(
			source,
			candidate,
		)

		self.assertEqual(baseline, 7)
		self.assertEqual(improved, 17)

	@patch(
		"recommendations.services.ProfileStrengthService.calculate_strength",
		return_value=0,
	)
	def test_discovery_score_uses_weighted_skill_relationships(
		self,
		_calculate_strength,
	):
		source = self.create_talent("source")
		candidate = self.create_talent("candidate")
		category = SkillCategory.objects.create(name="Sports")
		passing = Skill.objects.create(category=category, name="Passing")
		vision = Skill.objects.create(category=category, name="Vision")
		source.skills.add(passing)
		candidate.skills.add(vision)
		SkillRelationship.objects.create(
			skill=passing,
			related_skill=vision,
			strength="0.60",
		)

		score = RecommendationEngine.score_talent_for_discovery(
			source,
			candidate,
		)

		self.assertEqual(score, 3)

	@patch(
		"recommendations.services.ProfileStrengthService.calculate_strength",
		return_value=0,
	)
	def test_discovery_score_never_recommends_self(
		self,
		_calculate_strength,
	):
		talent = self.create_talent("self")

		self.assertEqual(
			RecommendationEngine.score_talent_for_discovery(
				talent,
				talent,
			),
			0,
		)

	def test_discovery_includes_candidates_with_related_skills(self):
		source = self.create_talent("source")
		candidate = self.create_talent("candidate")
		category = SkillCategory.objects.create(name="Sports")
		passing = Skill.objects.create(category=category, name="Passing")
		vision = Skill.objects.create(category=category, name="Vision")
		source.skills.add(passing)
		candidate.skills.add(vision)
		SkillRelationship.objects.create(
			skill=passing,
			related_skill=vision,
			strength="0.60",
		)

		recommendations = RecommendationEngine.recommend_talents_for_talent(
			source
		)

		self.assertEqual(
			[recommendation["talent"].pk for recommendation in recommendations],
			[candidate.pk],
		)
		self.assertIn("Vision", recommendations[0]["reasons"][0])

	def test_talent_discovery_excludes_non_public_profiles(self):
		source = self.create_talent("source")
		candidate = self.create_talent(
			"private_candidate",
			profile_visibility="PRIVATE",
		)
		domain = TalentDomain.objects.create(name="Sports")
		source.domains.add(domain)
		candidate.domains.add(domain)

		self.assertEqual(
			RecommendationEngine.recommend_talents_for_talent(source),
			[],
		)

	@patch(
		"recommendations.services.ProfileStrengthService.calculate_strength",
		return_value=0,
	)
	def test_event_certificates_contribute_to_discovery_score(
		self,
		_calculate_strength,
	):
		source = self.create_talent("source")
		candidate = self.create_talent("candidate")
		organization = Organization.objects.create(
			name="Event Organizer",
			country="Ghana",
		)
		now = timezone.now()
		event = Event.objects.create(
			organizer=organization,
			title="Sports Workshop",
			slug="sports-workshop",
			description="A workshop.",
			event_type="WORKSHOP",
			location="Accra",
			start_date=now,
			end_date=now + timedelta(days=1),
			registration_deadline=now,
		)
		EventCertificate.objects.create(
			event=event,
			talent=candidate,
			issued_by=organization,
			certificate_code="SPORTS-001",
		)

		self.assertEqual(
			RecommendationEngine.score_talent_for_discovery(
				source,
				candidate,
			),
			1,
		)

	def test_role_model_recommendations_exclude_non_public_profiles(self):
		source = self.create_talent("source")
		domain = TalentDomain.objects.create(name="Sports")
		source.domains.add(domain)
		private_role_model = self.create_talent(
			"private_role_model",
			is_role_model=True,
			profile_visibility="PRIVATE",
		)
		private_role_model.domains.add(domain)
		public_role_model = self.create_talent(
			"public_role_model",
			is_role_model=True,
			profile_visibility="PUBLIC",
		)
		public_role_model.domains.add(domain)

		recommendations = RecommendationEngine.recommend_role_models_for_talent(
			source
		)

		self.assertEqual(
			[recommendation["role_model"].pk for recommendation in recommendations],
			[public_role_model.pk],
		)


class OpportunityRecommendationTests(TestCase):
	def setUp(self):
		self.user = get_user_model().objects.create_user(username="talent")
		self.talent = TalentProfile.objects.create(
			user=self.user,
			country="Ghana",
			city="Accra",
			experience_level="EXPERT",
			preferred_work_type="REMOTE",
		)
		self.organization = Organization.objects.create(
			name="Example Organization",
			country="Ghana",
		)
		self.domain = TalentDomain.objects.create(name="Sports")
		self.opportunity = Opportunity.objects.create(
			organization=self.organization,
			title="Sports Analyst",
			description="Analyze match performance.",
			domain=self.domain,
			location="Accra, Ghana",
			work_type="REMOTE",
			experience_level="EXPERT",
		)

	@patch(
		"recommendations.services.ProfileStrengthService.calculate_strength",
		return_value=0,
	)
	def test_opportunity_score_weights_important_skills_and_fit(
		self,
		_calculate_strength,
	):
		category = SkillCategory.objects.create(name="Analysis")
		important_skill = Skill.objects.create(
			category=category,
			name="Performance Analysis",
		)
		other_skill = Skill.objects.create(
			category=category,
			name="Video Editing",
		)
		self.opportunity.skills.add(important_skill, other_skill)
		OpportunityRequirement.objects.create(
			opportunity=self.opportunity,
			skill=important_skill,
			importance=5,
		)
		OpportunityRequirement.objects.create(
			opportunity=self.opportunity,
			skill=other_skill,
			importance=1,
		)
		self.talent.domains.add(self.domain)
		self.talent.skills.add(important_skill)

		score = RecommendationEngine.calculate_score(
			self.talent,
			self.opportunity,
		)

		self.assertEqual(score, 75)

	def test_candidates_are_not_hard_filtered_by_country(self):
		remote_talent_user = get_user_model().objects.create_user(
			username="remote_talent",
		)
		remote_talent = TalentProfile.objects.create(
			user=remote_talent_user,
			country="Kenya",
		)
		remote_talent.domains.add(self.domain)

		candidates = RecommendationEngine.get_candidates(self.opportunity)

		self.assertIn(remote_talent, candidates)

	def test_organization_candidates_respect_profile_visibility(self):
		private_user = get_user_model().objects.create_user(
			username="private_talent",
		)
		private_talent = TalentProfile.objects.create(
			user=private_user,
			profile_visibility="PRIVATE",
		)
		private_talent.domains.add(self.domain)
		organization_only_user = get_user_model().objects.create_user(
			username="organization_talent",
		)
		organization_talent = TalentProfile.objects.create(
			user=organization_only_user,
			profile_visibility="ORGANIZATIONS",
		)
		organization_talent.domains.add(self.domain)

		candidates = RecommendationEngine.get_candidates(self.opportunity)

		self.assertNotIn(private_talent, candidates)
		self.assertIn(organization_talent, candidates)

	def test_opportunity_recommendations_exclude_expired_and_applied(self):
		past_opportunity = Opportunity.objects.create(
			organization=self.organization,
			title="Expired role",
			description="Expired.",
			domain=self.domain,
			deadline=timezone.localdate() - timedelta(days=1),
		)
		applied_opportunity = Opportunity.objects.create(
			organization=self.organization,
			title="Applied role",
			description="Already applied.",
			domain=self.domain,
			deadline=timezone.localdate() + timedelta(days=1),
		)
		available_opportunity = Opportunity.objects.create(
			organization=self.organization,
			title="Open role",
			description="Still accepting applications.",
			domain=self.domain,
			deadline=timezone.localdate() + timedelta(days=2),
		)
		Application.objects.create(
			talent=self.talent,
			opportunity=applied_opportunity,
		)

		recommendations = RecommendationEngine.recommend_opportunities_for_user(
			self.user
		)

		recommended_ids = {
			item["opportunity"].pk
			for item in recommendations
		}
		self.assertNotIn(past_opportunity.pk, recommended_ids)
		self.assertNotIn(applied_opportunity.pk, recommended_ids)
		self.assertIn(available_opportunity.pk, recommended_ids)


class CourseAndEventRecommendationTests(TestCase):
	def setUp(self):
		self.user = get_user_model().objects.create_user(username="learner")
		self.talent = TalentProfile.objects.create(user=self.user)
		self.domain = TalentDomain.objects.create(name="Sports")
		self.talent.domains.add(self.domain)
		self.creator = get_user_model().objects.create_user(username="creator")
		self.engine = RecommendationEngine()

	def test_course_recommendations_exclude_courses_already_enrolled_in(self):
		category = LearningCategory.objects.create(name="Sports")
		enrolled_course = Course.objects.create(
			creator=self.creator,
			category=category,
			title="Match Analysis",
			slug="match-analysis",
			description="Analyze sports performance.",
			status="APPROVED",
		)
		available_course = Course.objects.create(
			creator=self.creator,
			category=category,
			title="Coaching Skills",
			slug="coaching-skills",
			description="Develop sports coaching skills.",
			status="APPROVED",
		)
		Enrollment.objects.create(user=self.user, course=enrolled_course)

		recommendations = self.engine.recommend_courses_for_talent(self.talent)

		recommended_ids = {
			item["course"].pk
			for item in recommendations
		}
		self.assertNotIn(enrolled_course.pk, recommended_ids)
		self.assertIn(available_course.pk, recommended_ids)

	def test_event_recommendations_exclude_closed_registration(self):
		organization = Organization.objects.create(
			name="Event Organizer",
			country="Ghana",
		)
		now = timezone.now()
		event = Event.objects.create(
			organizer=organization,
			title="Sports Workshop",
			slug="closed-sports-workshop",
			description="A sports workshop.",
			event_type="WORKSHOP",
			location="Accra",
			start_date=now + timedelta(days=1),
			end_date=now + timedelta(days=2),
			registration_deadline=now - timedelta(seconds=1),
			status="PUBLISHED",
		)

		self.assertEqual(
			self.engine.recommend_events_for_talent(self.talent),
			[],
		)

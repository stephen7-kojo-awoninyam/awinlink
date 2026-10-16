from django.contrib.auth import get_user_model
from django.test import TestCase

from coaches.models import CoachProfile
from organizations.models import Organization, OrganizationCategory, OrganizationDomain
from recommendations.ecosystems import normalize_topic, recommend_sub_ecosystems
from recommendations.services import RecommendationEngine
from scouts.models import ScoutProfile
from skills.models import Skill, SkillCategory, SkillRelationship
from talents.models import TalentProfile


class TopicNormalizationTests(TestCase):
    def test_normalizes_unicode_spacing_punctuation_and_known_aliases(self):
        self.assertEqual(normalize_topic("  SCIENCE & Technology "), "science technology")
        self.assertEqual(normalize_topic("Football (Soccer)"), "soccer")
        self.assertEqual(normalize_topic("ＡＩ"), "artificial intelligence")


class SubEcosystemDiscoveryTests(TestCase):
    def make_user(self, username, role="ATHLETE"):
        return get_user_model().objects.create_user(username=username, role=role)

    def test_aliases_match_across_talent_and_coach_roles(self):
        athlete = self.make_user("soccer_talent")
        TalentProfile.objects.create(
            user=athlete,
            talent_category="SPORTS",
            talent_area="Football (Soccer)",
        )
        coach = self.make_user("soccer_coach", role="COACH")
        CoachProfile.objects.create(
            user=coach,
            coach_category="SPORTS",
            specialization="Association Football",
        )

        ecosystems = recommend_sub_ecosystems(athlete)

        soccer = next(item for item in ecosystems if item["focus"] == "soccer")
        self.assertEqual(soccer["member_count"], 2)
        self.assertEqual(soccer["member_types"], ["Coach", "Talent"])
        self.assertTrue(soccer["viewer_is_member"])
        self.assertIn("soccer", soccer["reason"].casefold())

    def test_scout_and_active_organization_profiles_share_topics(self):
        viewer = self.make_user("basketball_talent")
        TalentProfile.objects.create(user=viewer, talent_area="Basketball")
        scout = self.make_user("basketball_scout", role="SCOUT")
        ScoutProfile.objects.create(
            user=scout,
            scout_category="SPORTS",
            specialization="Basketball",
        )
        organization_user = self.make_user("basketball_org", role="ORGANIZATION")
        organization_category = OrganizationCategory.objects.create(name="Sports")
        organization_domain = OrganizationDomain.objects.create(
            category=organization_category,
            name="Basketball",
        )
        Organization.objects.create(
            user=organization_user,
            name="Basketball Club",
            category=organization_category,
            domain=organization_domain,
            country="Ghana",
            status="ACTIVE",
        )

        group = next(
            item for item in recommend_sub_ecosystems(viewer)
            if item["focus"] == "basketball"
        )
        self.assertEqual(group["member_count"], 3)
        self.assertEqual(group["member_types"], ["Organization", "Scout", "Talent"])

    def test_related_skill_strength_expands_interests_and_explains_community(self):
        category = SkillCategory.objects.create(name="Football")
        passing = Skill.objects.create(category=category, name="Passing")
        vision = Skill.objects.create(category=category, name="Vision")
        SkillRelationship.objects.create(
            skill=passing,
            related_skill=vision,
            strength="0.60",
        )
        source_user = self.make_user("passing_talent")
        source = TalentProfile.objects.create(user=source_user)
        source.skills.add(passing)
        candidate_user = self.make_user("vision_talent")
        candidate = TalentProfile.objects.create(user=candidate_user)
        candidate.skills.add(vision)

        ecosystems = RecommendationEngine.recommend_sub_ecosystems(source_user)

        vision_group = next(item for item in ecosystems if item["focus"] == "vision")
        self.assertEqual(vision_group["member_count"], 2)
        self.assertIn("active, discoverable members", vision_group["reason"])
        self.assertIn("related interest (strength 0.60)", vision_group["reason"])
        self.assertEqual(vision_group["score"], 47)

    def test_weak_skill_relationship_does_not_create_a_community(self):
        category = SkillCategory.objects.create(name="Sports")
        passing = Skill.objects.create(category=category, name="Passing")
        vision = Skill.objects.create(category=category, name="Vision")
        SkillRelationship.objects.create(
            skill=passing,
            related_skill=vision,
            strength="0.20",
        )
        viewer = self.make_user("weak_link_viewer")
        viewer_profile = TalentProfile.objects.create(user=viewer)
        viewer_profile.skills.add(passing)
        candidate = TalentProfile.objects.create(user=self.make_user("weak_link_candidate"))
        candidate.skills.add(vision)

        self.assertEqual(recommend_sub_ecosystems(viewer), [])

    def test_topics_overlap_and_minimum_size_counts_unique_public_users(self):
        category = SkillCategory.objects.create(name="Creative")
        design = Skill.objects.create(category=category, name="Design")
        writing = Skill.objects.create(category=category, name="Writing")
        viewer = self.make_user("multi_interest")
        viewer_profile = TalentProfile.objects.create(user=viewer)
        viewer_profile.skills.add(design, writing)
        for username, skill in (("design_member", design), ("writing_member", writing)):
            profile = TalentProfile.objects.create(user=self.make_user(username))
            profile.skills.add(skill)
        private_profile = TalentProfile.objects.create(
            user=self.make_user("private_design"),
            profile_visibility="PRIVATE",
        )
        private_profile.skills.add(design)

        groups = recommend_sub_ecosystems(viewer, minimum_members=2)
        by_focus = {item["focus"]: item for item in groups}
        self.assertIn("design", by_focus)
        self.assertIn("writing", by_focus)
        self.assertEqual(by_focus["design"]["member_count"], 2)
        self.assertNotIn("private_design", str(by_focus["design"]))
        self.assertEqual(recommend_sub_ecosystems(viewer, minimum_members=3), [])

    def test_private_related_profile_is_not_a_cross_role_member(self):
        viewer = self.make_user("public_viewer")
        viewer_profile = TalentProfile.objects.create(user=viewer, talent_area="Robotics")
        hidden_coach = self.make_user("hidden_coach", role="COACH")
        TalentProfile.objects.create(user=hidden_coach, profile_visibility="PRIVATE")
        CoachProfile.objects.create(
            user=hidden_coach,
            coach_category="SCIENCE_TECHNOLOGY",
            specialization="Robotics",
        )

        self.assertEqual(recommend_sub_ecosystems(viewer_profile.user), [])


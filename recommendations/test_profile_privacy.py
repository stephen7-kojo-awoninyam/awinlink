from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User, UserBlock
from analytics.models import RecommendationHistory
from organizations.models import Organization
from opportunities.models import Opportunity
from domains.models import TalentDomain
from talents.models import TalentProfile
from .services import RecommendationEngine


class RecommendationProfilePrivacyTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_user('matching-org-owner', role='ORGANIZATION')
        self.org = Organization.objects.create(user=self.actor, name='Matching org')
        domain, _ = TalentDomain.objects.get_or_create(name='Privacy regression domain')
        self.opportunity = Opportunity.objects.create(organization=self.org, title='Opportunity', domain=domain)
        self.owner = User.objects.create_user('matching-talent-marker', email='login-private@example.invalid')
        self.talent = TalentProfile.objects.create(user=self.owner)
        self.history = RecommendationHistory.objects.create(organization=self.org, opportunity=self.opportunity, talent=self.talent, score=90)
        self.api = APIClient(); self.api.force_authenticate(self.actor)

    def test_saved_discovery_recommendations_recheck_blocks_privacy_and_inactive_owners(self):
        path = f'/api/recommendations/{self.opportunity.pk}/'
        self.assertEqual(self.api.get(path).data[0]['talent_id'], self.talent.pk)
        for reverse in (False, True):
            block = UserBlock.objects.create(user=self.owner if reverse else self.actor, blocked_user=self.actor if reverse else self.owner)
            self.assertEqual(self.api.get(path).data, [])
            self.assertFalse(RecommendationEngine.get_candidates(self.opportunity).filter(pk=self.talent.pk).exists())
            block.delete()
        self.talent.profile_visibility = 'PRIVATE'; self.talent.save()
        self.assertEqual(self.api.get(path).data, [])
        self.talent.profile_visibility = 'PUBLIC'; self.talent.save()
        self.owner.is_active = False; self.owner.save()
        self.assertEqual(self.api.get(path).data, [])
        self.assertTrue(RecommendationHistory.objects.filter(pk=self.history.pk).exists())

    def test_organization_only_candidates_keep_current_capability_requirement(self):
        self.talent.profile_visibility = 'ORGANIZATIONS'; self.talent.save()
        self.assertTrue(RecommendationEngine.get_candidates(self.opportunity).filter(pk=self.talent.pk).exists())
        self.org.status = 'SUSPENDED'; self.org.save()
        self.assertFalse(RecommendationEngine.get_candidates(self.opportunity).filter(pk=self.talent.pk).exists())

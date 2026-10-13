from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from domains.models import TalentDomain
from opportunities.models import Opportunity
from organizations.models import Organization, OrganizationMembership
from recruitment.models import RecruitmentStage
from talents.models import TalentProfile
from .models import Shortlist


class RecruitmentAndShortlistCsrfTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(username='csrf_audit_owner', role='ORGANIZATION')
        cls.viewer = User.objects.create_user(username='csrf_audit_viewer', role='SCOUT')
        cls.talent_user = User.objects.create_user(username='csrf_audit_talent')
        cls.talent = TalentProfile.objects.create(user=cls.talent_user)
        cls.organization = Organization.objects.create(user=cls.owner, name='CSRF audit studio', country='GH')
        OrganizationMembership.objects.create(organization=cls.organization, user=cls.owner, role='OWNER')
        OrganizationMembership.objects.create(organization=cls.organization, user=cls.viewer, role='VIEWER')
        domain = TalentDomain.objects.create(name='CSRF audit domain')
        opportunity = Opportunity.objects.create(organization=cls.organization, domain=domain, title='CSRF audit opportunity')
        cls.stage = RecruitmentStage.objects.create(organization=cls.organization, talent=cls.talent, opportunity=opportunity)
        cls.shortlist = Shortlist.objects.create(organization=cls.organization, talent=cls.talent)

    def browser(self, user):
        client = Client(enforce_csrf_checks=True)
        client.force_login(user)
        client.get(reverse('login'))
        return client, client.cookies['csrftoken'].value

    def routes(self):
        return [reverse(name, args=[self.talent.pk]) for name in ('add_to_shortlist', 'remove_from_shortlist', 'toggle_star')] + [
            reverse('update_pipeline_stage', args=[self.stage.pk, 'SELECTED'])]

    def test_get_and_csrf_less_post_never_mutate_recruitment_or_shortlist(self):
        browser, _ = self.browser(self.owner)
        for route in self.routes():
            self.assertEqual(browser.get(route).status_code, 405)
            self.assertEqual(browser.post(route).status_code, 403)
        self.stage.refresh_from_db()
        self.shortlist.refresh_from_db()
        self.assertEqual(self.stage.stage, 'SHORTLISTED')
        self.assertFalse(self.shortlist.starred)

    def test_authorized_posts_keep_existing_stage_star_add_and_remove_actions(self):
        browser, csrf = self.browser(self.owner)
        data = {'csrfmiddlewaretoken': csrf}
        self.assertEqual(browser.post(reverse('toggle_star', args=[self.talent.pk]), data).status_code, 302)
        self.shortlist.refresh_from_db()
        self.assertTrue(self.shortlist.starred)
        self.assertEqual(browser.post(reverse('update_pipeline_stage', args=[self.stage.pk, 'SELECTED']), data).status_code, 302)
        self.stage.refresh_from_db()
        self.assertEqual(self.stage.stage, 'SELECTED')
        self.assertEqual(browser.post(reverse('remove_from_shortlist', args=[self.talent.pk]), data).status_code, 302)
        self.assertFalse(Shortlist.objects.filter(pk=self.shortlist.pk).exists())
        self.assertEqual(browser.post(reverse('add_to_shortlist', args=[self.talent.pk]), data).status_code, 302)
        self.assertEqual(Shortlist.objects.filter(organization=self.organization, talent=self.talent).count(), 1)

    def test_viewer_capability_is_still_denied_with_valid_csrf(self):
        browser, csrf = self.browser(self.viewer)
        for route in self.routes():
            self.assertEqual(browser.post(route, {'csrfmiddlewaretoken': csrf}).status_code, 403)

    def test_existing_management_templates_submit_post_with_csrf(self):
        self.client.force_login(self.owner)
        for name in ('organization_shortlist', 'recruitment_pipeline'):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'method="post"')
            self.assertContains(response, 'name="csrfmiddlewaretoken"')
            self.assertNotContains(response, 'href="/recruitment/update/')
            self.assertNotContains(response, 'href="/shortlists/toggle-star/')

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import resolve, reverse
from django.utils import timezone

from accounts.models import ContentReport


class ChildSafetyPageTests(TestCase):
    @override_settings(AWINLINK_CHILD_SAFETY_EMAIL='stephenkojoawoninyam@gmail.com')
    def test_designated_address_is_visible_without_claiming_delivery_or_monitoring(self):
        for url in ['/child-safety/', '/child-safety/report/', '/support/', '/community-guidelines/']:
            response = self.client.get(url)
            self.assertContains(response, 'mailto:stephenkojoawoninyam@gmail.com')
            self.assertContains(response, 'Mailbox monitoring and email delivery have not been verified.')
            self.assertContains(response, 'Draft for legal review.')
            self.assertContains(response, 'data-legal-status="draft"')
    def test_anonymous_page_is_public_html_http_200_without_login_or_side_effects(self):
        url = reverse('child_safety')
        self.assertEqual(url, '/child-safety/')
        self.assertEqual(resolve(url).kwargs['page'], 'child-safety')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/html', response['Content-Type'])
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertTemplateUsed(response, 'core/public_page.html')
        self.assertTemplateUsed(response, 'core/policies/child_safety.html')
        self.assertContains(response, '<h1>Child Safety Standards</h1>', html=True)
        self.assertContains(response, 'Awinlink')
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertFalse(ContentReport.objects.exists())
        self.assertEqual(self.client.head(url).status_code, 200)
        self.assertEqual(self.client.post(url, {}).status_code, 405)

    def test_responsive_page_has_section_navigation_and_no_external_scripts(self):
        response = self.client.get('/child-safety/')
        self.assertContains(response, 'name="viewport" content="width=device-width, initial-scale=1"')
        self.assertContains(response, '@media(max-width:600px)')
        self.assertContains(response, 'grid-template-columns:1fr')
        self.assertContains(response, 'aria-label="Child safety sections"')
        for section in ['prohibited', 'reporting', 'moderation', 'legal-escalation', 'before-release']:
            self.assertContains(response, f'id="{section}"')
            self.assertContains(response, f'href="#{section}"')
        for route in ['privacy', 'terms', 'community_guidelines', 'support', 'child_safety']:
            self.assertContains(response, f'href="{reverse(route)}"')
        self.assertNotContains(response, '<script')

    def test_rules_reporting_and_unimplemented_safeguards_are_explicit(self):
        response = self.client.get('/child-safety/')
        for text in ['Zero tolerance', 'CSAE', 'CSAM', 'groom', 'sexually extort',
                     'Do not download, forward or attach suspected CSAM',
                     'Reports require a signed-in account', 'unsafe',
                     'does not submit a report', 'does not automatically remove content',
                     'No automated law-enforcement reporting', 'verify staff monitoring',
                     'missing child-facing safety reminder', 'compliance is not yet claimed']:
            self.assertContains(response, text)
        self.assertContains(response, 'Draft for legal review.')
        self.assertContains(response, 'data-legal-status="draft"')

    @override_settings(AWINLINK_CHILD_SAFETY_EMAIL='', AWINLINK_SUPPORT_EMAIL='')
    def test_missing_safety_and_support_contacts_are_not_invented(self):
        response = self.client.get('/child-safety/')
        self.assertContains(response, 'Not yet configured:')
        self.assertContains(response, 'support email has not yet been configured')
        self.assertNotContains(response, 'mailto:')

    @override_settings(AWINLINK_CHILD_SAFETY_EMAIL='safety@example.com', AWINLINK_SUPPORT_EMAIL='help@example.com')
    def test_configured_contacts_do_not_remove_draft_or_compliance_blockers(self):
        response = self.client.get('/child-safety/')
        self.assertContains(response, 'mailto:safety@example.com')
        self.assertContains(response, 'mailto:help@example.com')
        self.assertContains(response, 'Draft standards')
        self.assertContains(response, 'Outstanding safeguards before a compliance claim')

    def test_restricted_minor_can_read_standards_without_unrestricting_account(self):
        user = get_user_model().objects.create_user(username='restricted-safety-reader', is_active=True,
            date_of_birth=date(timezone.localdate().year - 10, 1, 1))
        self.client.force_login(user)
        self.assertEqual(self.client.get('/child-safety/').status_code, 200)
        self.assertEqual(self.client.head('/child-safety/').status_code, 200)
        self.assertEqual(self.client.post('/child-safety/', {}).status_code, 403)
        self.assertEqual(self.client.get('/api/auth/me/').status_code, 403)
        self.assertFalse(ContentReport.objects.exists())

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from accounts.legal import TERMS_VERSION
from datetime import date
from django.utils import timezone


class PublicReleasePagesTests(TestCase):
    def test_restricted_minor_can_read_public_legal_pages_but_cannot_mutate(self):
        user = get_user_model().objects.create_user(username='pending-reader', is_active=True,
            date_of_birth=date(timezone.localdate().year - 10, 1, 1))
        self.client.force_login(user)
        for page in ['privacy', 'terms', 'community-guidelines', 'child-safety', 'support', 'delete-account']:
            self.assertEqual(self.client.get(f'/{page}/').status_code, 200)
            self.assertEqual(self.client.head(f'/{page}/').status_code, 200)
        self.assertNotContains(self.client.get('/delete-account/'), 'name="auth_method"')
        self.assertEqual(self.client.post('/delete-account/', {'confirm': 'yes'}).status_code, 403)
        self.assertEqual(self.client.post('/accounts/google/start/', {'purpose': 'DELETE'}).status_code, 403)
        self.assertTrue(get_user_model().objects.filter(pk=user.pk).exists())

    def test_previous_terms_acceptance_is_not_silently_rewritten(self):
        before = timezone.now()
        user = get_user_model().objects.create_user(username='previous-terms',
            terms_accepted_version='2026-10-18-draft-1', terms_accepted_at=before)
        self.client.force_login(user)
        self.client.get('/terms/')
        user.refresh_from_db()
        self.assertEqual(user.terms_accepted_version, '2026-10-18-draft-1')
        self.assertEqual(user.terms_accepted_at, before)
    def test_every_legal_page_retains_draft_warning_and_current_version(self):
        for page in ['privacy', 'terms', 'community-guidelines', 'child-safety', 'support', 'delete-account']:
            response = self.client.get(f'/{page}/')
            self.assertContains(response, 'data-legal-status="draft"')
            self.assertContains(response, 'Draft for legal review.')
            self.assertContains(response, TERMS_VERSION)
            self.assertContains(response, 'No effective date or legal approval is asserted')

    @override_settings(AWINLINK_LEGAL_OPERATOR='Test operator', AWINLINK_LEGAL_ADDRESS='Test address',
                       AWINLINK_SUPPORT_EMAIL='support@example.com', AWINLINK_PRIVACY_EMAIL='privacy@example.com',
                       AWINLINK_CHILD_SAFETY_EMAIL='safety@example.com')
    def test_configured_details_are_visible_but_cannot_approve_drafts(self):
        response = self.client.get('/support/')
        for value in ['Test operator', 'Test address', 'mailto:support@example.com', 'mailto:privacy@example.com', 'mailto:safety@example.com']:
            self.assertContains(response, value)
        self.assertNotContains(response, 'Release information is awaiting completion')
        self.assertContains(response, 'Draft for legal review.')
        self.assertContains(self.client.get('/privacy/'), 'mailto:privacy@example.com')

    @override_settings(AWINLINK_LEGAL_OPERATOR='', AWINLINK_LEGAL_ADDRESS='', AWINLINK_SUPPORT_EMAIL='',
                       AWINLINK_PRIVACY_EMAIL='', AWINLINK_CHILD_SAFETY_EMAIL='')
    def test_missing_operator_details_are_explicit_without_invented_contacts(self):
        response = self.client.get('/support/')
        self.assertContains(response, 'Release information is awaiting completion')
        self.assertContains(response, 'public support email has not yet been configured')
        self.assertContains(response, 'privacy contact has not yet been configured')
        self.assertContains(response, 'child-safety contact has not yet been configured')
        self.assertNotContains(response, 'mailto:')

    @override_settings(AWINLINK_LEGAL_OPERATOR='<script>alert(1)</script>', AWINLINK_LEGAL_ADDRESS='<img src=x>',
                       AWINLINK_SUPPORT_EMAIL='bad?subject=unsafe', AWINLINK_PRIVACY_EMAIL='bad\nvalue',
                       AWINLINK_CHILD_SAFETY_EMAIL='javascript:alert(1)')
    def test_operator_text_is_escaped_and_invalid_contacts_are_not_links(self):
        response = self.client.get('/support/')
        self.assertNotContains(response, '<script>')
        self.assertNotContains(response, '<img src=x>')
        self.assertNotContains(response, 'mailto:')
        self.assertContains(response, 'Release information is awaiting completion')

    def test_privacy_discloses_age_guardians_providers_and_real_retention_limits(self):
        response = self.client.get('/privacy/')
        for text in ['under 13', '13–17', 'nominated guardian email', 'verification time and case reference',
                     'before approval', 'unknown-age', 'manual process', 'not account deletion',
                     'Cloudinary', 'Resend', 'Paystack', 'Expo', 'FCM', 'APNs', 'TURN',
                     'cleanup command', 'not promises', 'not all automatically erased', 'shared classroom',
                     'authentica', 'five minutes']:
            self.assertContains(response, text, count=None)
        self.assertNotContains(response, 'are removed by scheduled cleanup')

    def test_child_safety_and_google_deletion_instructions_are_public(self):
        response = self.client.get('/community-guidelines/')
        for text in ['id="child-safety"', 'CSAE', 'CSAM', 'grooming', 'sextortion', 'Play Console', 'do not download']:
            self.assertContains(response, text, count=None)
        self.assertContains(self.client.get('/support/'), 'without setting an Awinlink password')
        self.assertContains(self.client.get('/delete-account/'), 'retention details')

    def test_public_pages_are_accessible_without_login(self):
        for page in ['privacy', 'terms', 'child-safety', 'support', 'delete-account']:
            response = self.client.get(f'/{page}/')
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'Awinlink')
            self.assertEqual(response['Cache-Control'], 'no-store')

    @override_settings(AWINLINK_SUPPORT_EMAIL='help@example.com', AWINLINK_LEGAL_OPERATOR='Test operator')
    def test_support_uses_configured_contact(self):
        self.assertContains(self.client.get('/support/'), 'mailto:help@example.com')

    def test_browser_deletion_requires_authentication_password_and_confirmation(self):
        user = get_user_model().objects.create_user(username='delete-web', password='Secret123!')
        self.assertEqual(self.client.post('/delete-account/', {'password': 'Secret123!', 'confirm': 'yes'}).status_code, 400)
        response = self.client.post('/delete-account/sign-in/', {'username': user.username, 'password': 'Secret123!'})
        self.assertRedirects(response, '/delete-account/')
        self.assertEqual(self.client.post('/delete-account/', {'password': 'wrong', 'confirm': 'yes'}).status_code, 400)
        self.assertEqual(self.client.post('/delete-account/', {'password': 'Secret123!'}).status_code, 400)
        self.assertContains(self.client.post('/delete-account/', {'password': 'Secret123!', 'confirm': 'yes'}), 'has been deleted')
        self.assertFalse(get_user_model().objects.filter(pk=user.pk).exists())

    def test_browser_deletion_rejects_csrf_and_non_deletion_posts(self):
        self.assertEqual(Client(enforce_csrf_checks=True).post('/delete-account/').status_code, 403)
        self.assertEqual(self.client.post('/privacy/').status_code, 405)

    def test_browser_deletion_preserves_organization_owner(self):
        from organizations.models import Organization
        user = get_user_model().objects.create_user(username='owner-web', password='Secret123!')
        Organization.objects.create(user=user, name='Owner organization')
        self.client.force_login(user)
        self.assertContains(self.client.post('/delete-account/', {'password': 'Secret123!', 'confirm': 'yes'}), 'Transfer organization ownership', status_code=400)
        self.assertTrue(get_user_model().objects.filter(pk=user.pk).exists())

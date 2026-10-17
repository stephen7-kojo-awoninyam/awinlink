from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings


class PublicReleasePagesTests(TestCase):
    def test_public_pages_are_accessible_without_login(self):
        for page in ['privacy', 'terms', 'support', 'delete-account']:
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

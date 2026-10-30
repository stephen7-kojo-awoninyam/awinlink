import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from django.contrib.admin.sites import AdminSite
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.test import RequestFactory, TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import User
from config.media_storage import PlaybackMediaStorage
from config.media_views import _media_is_allowed
from .admin import VerificationRequestAdmin
from .models import TalentProfile, VerificationRequest


class VerificationDocumentSecurityTests(TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        override = override_settings(MEDIA_ROOT=directory.name, STORAGES={
            'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
        override.enable(); self.addCleanup(override.disable)
        self.owner = User.objects.create_user('proof-owner', role='ATHLETE')
        self.viewer = User.objects.create_user('proof-viewer', role='COACH')
        self.admin = User.objects.create_user('proof-reviewer', role='ADMIN')
        self.superuser = User.objects.create_user('proof-super', is_superuser=True, is_staff=True)
        self.talent = TalentProfile.objects.create(user=self.owner)
        self.data = b'%PDF-1.7\nprivate evidence\n%%EOF'
        self.name = FileSystemStorage().save('verification_documents/proof.pdf', ContentFile(self.data))
        self.verification = VerificationRequest.objects.create(talent=self.talent, document=self.name)
        self.url = '/media/' + self.name
        self.api = APIClient()

    def assert_response(self, user, status, method='get', **headers):
        self.api.force_authenticate(user)
        response = getattr(self.api, method)(self.url, **headers)
        self.assertEqual(response.status_code, status)
        self.assertIn('no-store', response['Cache-Control'])
        if status in (200, 206):
            self.assertIn('attachment', response['Content-Disposition'])
            self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
            if method != 'head':
                self.assertEqual(b''.join(response.streaming_content), self.data if status == 200 else self.data[:5])
        response.close()

    def test_owner_and_legitimate_reviewers_keep_original_bytes_for_all_review_statuses(self):
        for status in ('PENDING', 'APPROVED', 'REJECTED'):
            self.verification.status = status; self.verification.save(update_fields=['status'])
            for user in (self.owner, self.admin, self.superuser):
                with self.subTest(status=status, user=user.username):
                    self.assert_response(user, 200)
                    self.assert_response(user, 200, 'head')
                    self.assert_response(user, 206, HTTP_RANGE='bytes=0-4')

    def test_anonymous_other_roles_and_staff_flags_cannot_read_evidence(self):
        self.assert_response(None, 404)
        for role in ('ATHLETE', 'COACH', 'SCOUT', 'ORGANIZATION'):
            self.viewer.role = role; self.viewer.is_staff = True; self.viewer.save()
            self.assert_response(self.viewer, 404)
            self.assert_response(self.viewer, 404, 'head')
            self.assert_response(self.viewer, 404, HTTP_RANGE='bytes=0-4')

    def test_revoked_admin_and_disabled_owner_are_checked_from_database(self):
        stale_admin = User.objects.get(pk=self.admin.pk)
        User.objects.filter(pk=self.admin.pk).update(role='COACH')
        self.assertFalse(_media_is_allowed(stale_admin, self.name))
        for user in (self.owner, self.superuser):
            User.objects.filter(pk=user.pk).update(is_active=False)
            self.assertFalse(_media_is_allowed(user, self.name))

    def test_unreferenced_evidence_denied_even_to_reviewers_without_deleting_bytes(self):
        self.verification.delete()
        for user in (self.owner, self.admin, self.superuser):
            self.assert_response(user, 404)
        self.assertEqual(Path(FileSystemStorage().path(self.name)).read_bytes(), self.data)

    def test_privacy_and_block_settings_do_not_remove_owner_or_reviewer_evidence_access(self):
        from accounts.models import UserBlock
        self.talent.profile_visibility = 'PRIVATE'; self.talent.save()
        UserBlock.objects.create(user=self.owner, blocked_user=self.admin)
        self.assert_response(self.owner, 200)
        self.assert_response(self.admin, 200)

    def test_mobile_jwt_has_the_same_acl(self):
        for user, status in ((self.owner, 200), (self.viewer, 404), (self.admin, 200)):
            client = APIClient(); client.credentials(HTTP_AUTHORIZATION='Bearer ' + str(AccessToken.for_user(user)))
            response = client.get(self.url); self.assertEqual(response.status_code, status); response.close()

    def test_cloud_denials_never_fetch_and_authorized_response_never_exposes_signed_url(self):
        storage = PlaybackMediaStorage()
        self.verification.document = 'media/verification_documents/provider-proof'; self.verification.save()
        self.url = '/media/verification_documents/provider-proof'
        session = Mock(); response = Mock(status_code=200)
        response.headers = {'Content-Type': 'application/pdf', 'Content-Length': str(len(self.data))}
        response.iter_content.return_value = iter([self.data]); session.get.return_value = response
        with patch('config.media_views.default_storage', storage), patch('config.media_views.requests.Session', return_value=session), patch(
                'config.media_views._cloud_url', return_value='https://provider.invalid/signed-secret') as url:
            self.api.force_authenticate(self.viewer)
            self.assertEqual(self.api.get(self.url).status_code, 404); session.get.assert_not_called()
            self.api.force_authenticate(self.owner)
            result = self.api.get(self.url)
            self.assertEqual(result.status_code, 200)
            self.assertNotIn('signed-secret', str(result.headers))
            self.assertEqual(b''.join(result.streaming_content), self.data)
            self.assertTrue(url.call_args.kwargs['authenticated']); result.close()

    def test_reviewer_pages_are_not_cacheable_and_use_application_document_urls(self):
        self.client.force_login(self.admin)
        from django.urls import reverse
        response = self.client.get(reverse('verification_requests'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertContains(response, self.url)
        self.assertContains(response, 'noopener noreferrer')

    def test_django_admin_model_permissions_do_not_grant_nonreviewers_document_management(self):
        admin = VerificationRequestAdmin(VerificationRequest, AdminSite())
        request = RequestFactory().get('/admin/')
        self.viewer.is_staff = True; request.user = self.viewer
        for method in ('has_view_permission', 'has_change_permission', 'has_add_permission', 'has_delete_permission'):
            self.assertFalse(getattr(admin, method)(request))
        request.user = self.superuser
        self.assertTrue(admin.has_view_permission(request))

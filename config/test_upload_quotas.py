import tempfile
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import User
from feed.models import Post
from .resource_limits import Lease, ResourceUnavailable


MP4 = b'\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isommp42' + b'\x00' * 16


@override_settings(SECURE_SSL_REDIRECT=False)
class UploadQuotaTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory(); self.addCleanup(self.media.cleanup)
        limits = {**settings.AWINLINK_RESOURCE_LIMITS, 'upload_bytes': (60, 3600)}
        override = override_settings(MEDIA_ROOT=self.media.name, AWINLINK_RESOURCE_LIMITS=limits)
        override.enable(); self.addCleanup(override.disable)
        self.user = User.objects.create_user('quota-owner')
        self.other = User.objects.create_user('quota-other')
        self.api = APIClient()
        self.api.credentials(HTTP_AUTHORIZATION='Bearer ' + str(AccessToken.for_user(self.user)))

    def upload(self, api=None, data=MP4):
        return (api or self.api).post('/api/feed/posts/create/', {
            'caption': 'Quota fixture', 'video': SimpleUploadedFile('clip.mp4', data, 'video/mp4'),
        }, format='multipart')

    def test_shared_byte_budget_returns_retry_and_preserves_existing_file(self):
        first = self.upload(); self.assertEqual(first.status_code, 201)
        saved = Post.objects.get().video.path; original = Path(saved).read_bytes()
        denied = self.upload(); self.assertEqual(denied.status_code, 429)
        self.assertIn('Retry-After', denied)
        self.assertEqual(Post.objects.count(), 1); self.assertEqual(Path(saved).read_bytes(), original)
        self.assertEqual(len(list(Path(self.media.name).rglob('*.mp4'))), 1)
        other = APIClient(); other.credentials(HTTP_AUTHORIZATION='Bearer ' + str(AccessToken.for_user(self.other)))
        self.assertEqual(self.upload(other).status_code, 201)

    def test_browser_and_native_uploads_share_account_budget(self):
        self.assertEqual(self.upload().status_code, 201)
        browser = APIClient(); browser.force_login(self.user)
        self.assertEqual(self.upload(browser).status_code, 429)

    def test_failed_content_is_charged_and_cannot_reset_budget(self):
        self.assertEqual(self.upload(data=b'not a video' * 4).status_code, 400)
        self.assertEqual(self.upload().status_code, 429)
        self.assertFalse(Post.objects.exists())

    def test_parallel_upload_slot_exhaustion_is_controlled_and_released(self):
        held = [Lease('upload_connections', 'user:' + str(self.user.pk)).acquire() for _ in range(4)]
        try:
            self.assertEqual(self.upload().status_code, 429)
            held[0].release()
            self.assertEqual(self.upload().status_code, 201)
        finally:
            for lease in held: lease.release()

    def test_upload_protection_outage_is_503_without_persisting_or_disclosing_credentials(self):
        with patch('config.upload_handlers.consume', side_effect=ResourceUnavailable()):
            response = self.upload()
        self.assertEqual(response.status_code, 503)
        self.assertFalse(Post.objects.exists())
        self.assertNotIn('redis://', response.content.decode())
        # The failed request releases both leases, so a legitimate retry works.
        self.assertEqual(self.upload().status_code, 201)

    def test_metadata_only_edits_do_not_consume_upload_slots(self):
        with patch('config.upload_handlers.Lease', side_effect=AssertionError('No file uploaded')):
            response = self.api.post('/api/feed/posts/create/', {'caption': 'Text only'}, format='json')
        self.assertEqual(response.status_code, 201)

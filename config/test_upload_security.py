import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from config.media_storage import LocalPlaybackStorage, PlaybackMediaStorage
from config.upload_security import UnsafeUpload, validate_header, validate_stored_upload
from feed.models import Post
from learning.models import Course, Enrollment, LearningCategory, Lesson
from messaging.models import Conversation, ConversationParticipant, Message
from talents.models import TalentProfile, VerificationRequest


MP4 = b'\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isommp42' + b'\x00' * 16
WEBM = b'\x1aE\xdf\xa3' + b'webm-fixture' * 3
PDF = b'%PDF-1.7\nfixture document\n%%EOF'
HTML = b'<!doctype html><script>window.auditMarker=true</script>'


class UploadPolicyTests(SimpleTestCase):
    def test_raster_recording_video_document_signatures_and_mobile_containers(self):
        samples = [('clip.mp4', MP4, 'video'), ('camera.mov', MP4, 'video'),
            ('voice.m4a', MP4, 'audio'), ('voice.mp4', MP4, 'audio'),
            ('recording.webm', WEBM, 'audio'), ('clip.webm', WEBM, 'video'),
            ('voice.ogg', b'OggSrecording', 'audio'), ('voice.mp3', b'ID3recording', 'audio'),
            ('notes.pdf', PDF, 'file'), ('notes.txt', b'Lesson notes', 'file'),
            ('sheet.xlsx', b'PK\x03\x04spreadsheet', 'file'),
            ('photo.png', b'\x89PNG\r\n\x1a\nfixture', 'image')]
        for name, data, kind in samples:
            with self.subTest(name=name):
                validate_header(name, data, len(data), kind)

    def test_active_extensions_and_forged_media_signatures_are_rejected(self):
        for name, kind in [('payload.html', 'file'), ('payload.HTML', 'video'),
            ('payload.svg', 'image'), ('payload.xhtml', 'file'), ('payload.xml', 'file'),
            ('payload.js', 'file'), ('payload.exe', 'file'), ('payload.mp4', 'video'),
            ('payload.jpg', 'image'), ('payload.pdf', 'file'), ('payload.mp3', 'audio')]:
            with self.subTest(name=name), self.assertRaises(UnsafeUpload):
                validate_header(name, HTML, len(HTML), kind)

    def test_file_extension_must_match_allowed_kind(self):
        for name, data, kind in [('notes.pdf', PDF, 'video'), ('voice.mp3', b'ID3audio', 'image')]:
            with self.subTest(name=name), self.assertRaises(UnsafeUpload):
                validate_header(name, data, len(data), kind)

    @override_settings(AWINLINK_UPLOAD_LIMITS={'video': 24})
    def test_per_kind_limits_are_enforced(self):
        with self.assertRaises(UnsafeUpload):
            validate_header('clip.mp4', MP4, len(MP4), 'video')

    def test_storage_validation_preserves_stream_cursor_and_file_bytes(self):
        content = ContentFile(MP4, name='clip.mp4')
        content.seek(7)
        validate_stored_upload('feed/videos/clip.mp4', content)
        self.assertEqual(content.tell(), 7)
        content.seek(0)
        self.assertEqual(content.read(), MP4)

    def test_local_storage_refuses_new_html_without_touching_existing_file(self):
        with tempfile.TemporaryDirectory() as media:
            old = FileSystemStorage(location=media)
            name = old.save('feed/videos/legacy.html', ContentFile(HTML))
            storage = LocalPlaybackStorage(location=media)
            with self.assertRaises(ValidationError):
                storage.save(name, ContentFile(HTML))
            self.assertEqual(Path(old.path(name)).read_bytes(), HTML)
            self.assertEqual(len(list(Path(media).rglob('*.html'))), 1)

    @patch('cloudinary.uploader.upload')
    def test_cloud_storage_validates_before_network_and_keeps_raw_documents_downloads(self, upload):
        storage = PlaybackMediaStorage()
        with self.assertRaises(ValidationError):
            storage._upload('feed/videos/attack.mp4', ContentFile(HTML))
        upload.assert_not_called()
        storage._upload('messages/files/notes.pdf', ContentFile(PDF))
        self.assertEqual(upload.call_args.kwargs['resource_type'], 'raw')
        self.assertEqual(upload.call_args.kwargs['type'], 'authenticated')
        self.assertEqual(upload.call_args.kwargs['flags'], 'attachment')

    @patch('cloudinary.uploader.upload')
    def test_new_verification_documents_are_authenticated(self, upload):
        PlaybackMediaStorage()._upload('verification_documents/proof.pdf', ContentFile(PDF))
        self.assertEqual(upload.call_args.kwargs['type'], 'authenticated')

    def test_cloud_storage_open_size_and_exists_use_provider_urls_not_app_urls(self):
        remote = Mock(status_code=200)
        remote.headers = {'Content-Length': str(len(PDF))}
        remote.iter_content.return_value = iter([PDF])
        with patch('config.media_views._cloud_url', return_value='https://cloudinary.invalid/signed-proof') as url, \
             patch('requests.Session.get', return_value=remote) as get, \
             patch('requests.Session.head', return_value=remote) as head:
            storage = PlaybackMediaStorage()
            with storage.open('verification_documents/proof.pdf') as opened:
                self.assertEqual(opened.read(), PDF)
            self.assertEqual(storage.size('verification_documents/proof.pdf'), len(PDF))
            self.assertTrue(storage.exists('verification_documents/proof.pdf'))
            self.assertTrue(url.call_args.kwargs['authenticated'])
            self.assertTrue(get.call_args.args[0].startswith('https://'))
            self.assertTrue(head.call_args.args[0].startswith('https://'))


@override_settings(STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}, SECURE_SSL_REDIRECT=False)
class UploadAndDeliverySecurityTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        override = override_settings(MEDIA_ROOT=self.media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.owner = User.objects.create_user('secure-media-owner')
        self.other = User.objects.create_user('secure-media-other')
        self.api = APIClient()
        self.api.force_authenticate(self.owner)
        self.conversation = Conversation.objects.create(created_by=self.owner)
        ConversationParticipant.objects.create(conversation=self.conversation, user=self.owner)

    def assert_inert(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/octet-stream')
        self.assertTrue(response['Content-Disposition'].startswith('attachment;'))
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertIn('sandbox', response['Content-Security-Policy'])

    def reference_portfolio(self, path):
        from portfolio.models import PortfolioItem
        talent, _ = TalentProfile.objects.get_or_create(user=self.owner)
        PortfolioItem.objects.create(talent=talent, title='Delivery fixture', item_type='DOCUMENT',
            **({'image': path} if path.startswith('portfolio/images/') else {'file': path}))

    def reference_profile_asset(self, path):
        if path.startswith('talents/profile/'):
            talent, _ = TalentProfile.objects.get_or_create(user=self.owner)
            talent.profile_photo = path; talent.save()
        elif path.startswith('athletes/'):
            from athletes.models import AthleteProfile, AthleteMedia
            from datetime import date
            athlete, _ = AthleteProfile.objects.get_or_create(user=self.owner,
                defaults={'date_of_birth': date(2000, 1, 1), 'height': 180, 'weight': 70})
            AthleteMedia.objects.create(athlete=athlete, title='Legacy fixture', media_type='IMAGE', file=path)
        elif path.startswith('events/'):
            from events.models import Event, EventMedia
            from organizations.models import Organization
            from django.utils import timezone
            org, _ = Organization.objects.get_or_create(user=self.owner, defaults={'name': 'Fixture org'})
            event = Event.objects.create(organizer=org, title='Legacy fixture', slug='legacy-fixture',
                status='PUBLISHED', start_date=timezone.now(), end_date=timezone.now(), registration_deadline=timezone.now())
            EventMedia.objects.create(event=event, uploaded_by=org, media_type='IMAGE', file=path)

    def test_original_api_exploit_and_spoofed_mime_are_rejected_before_post_creation(self):
        for name, mime in [('attack.html', 'text/html'), ('attack.mp4', 'video/mp4'),
                            ('attack.mp4', 'application/octet-stream')]:
            with self.subTest(name=name, mime=mime):
                response = self.api.post('/api/feed/posts/create/', {'caption': 'test',
                    'video': SimpleUploadedFile(name, HTML, mime)}, format='multipart')
                self.assertEqual(response.status_code, 400)
                self.assertIn('detail', response.json())
        self.assertFalse(Post.objects.exists())
        self.assertFalse(list(Path(self.media.name).rglob('*.*')))

    def test_web_upload_rejects_html_before_persistence(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.owner)
        browser.get('/onboarding/role/')
        response = browser.post('/api/feed/posts/create/', {'caption': 'test',
            'csrfmiddlewaretoken': browser.cookies['csrftoken'].value,
            'video': SimpleUploadedFile('attack.mp4', HTML, 'video/mp4')})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Post.objects.exists())

    def test_valid_upload_still_requires_csrf_for_browser_session(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.owner)
        response = browser.post('/api/feed/posts/create/', {'caption': 'test',
            'video': SimpleUploadedFile('clip.mp4', MP4, 'video/mp4')})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Post.objects.exists())

    def test_authenticated_native_video_upload_is_preserved(self):
        response = self.api.post('/api/feed/posts/create/', {'caption': 'safe clip',
            'video': SimpleUploadedFile('camera.mov', MP4, 'video/quicktime')}, format='multipart')
        self.assertEqual(response.status_code, 201, getattr(response, 'data', None))
        post = Post.objects.get(pk=response.data['id'])
        with post.video.open() as media:
            self.assertEqual(media.read(), MP4)
        served = self.api.get(post.video.url)
        self.assertEqual(served['Content-Type'], 'video/quicktime')
        self.assertEqual(b''.join(served.streaming_content), MP4)

    def test_message_uploads_reject_html_as_document_audio_and_video(self):
        url = f'/api/messaging/conversations/{self.conversation.pk}/messages/create/'
        for field, name in [('file', 'attack.html'), ('audio', 'attack.mp3'), ('video', 'attack.webm')]:
            with self.subTest(field=field):
                response = self.api.post(url, {'message_type': field.upper(),
                    field: SimpleUploadedFile(name, HTML, 'application/octet-stream')}, format='multipart')
                self.assertEqual(response.status_code, 400)
        self.assertFalse(Message.objects.exists())

    def test_legitimate_pdf_and_text_with_markup_remain_downloadable(self):
        url = f'/api/messaging/conversations/{self.conversation.pk}/messages/create/'
        for name, data in [('lesson.pdf', PDF), ('.notes.txt', HTML)]:
            with self.subTest(name=name):
                response = self.api.post(url, {'message_type': 'FILE',
                    'file': SimpleUploadedFile(name, data)}, format='multipart')
                self.assertEqual(response.status_code, 201, getattr(response, 'data', None))
                served = self.api.get(response.data['file'])
                self.assert_inert(served)
                self.assertEqual(b''.join(served.streaming_content), data)

    @override_settings(AWINLINK_UPLOAD_LIMITS={'video': 24})
    def test_streaming_size_limit_does_not_save_partial_upload(self):
        response = self.api.post('/api/feed/posts/create/', {'caption': 'large',
            'video': SimpleUploadedFile('clip.mp4', MP4, 'video/mp4')}, format='multipart')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Post.objects.exists())

    @override_settings(AWINLINK_UPLOAD_TOTAL_BYTES=60)
    def test_request_total_limit_counts_multiple_files(self):
        response = self.api.post('/api/feed/posts/create/', {'caption': 'total',
            'video': SimpleUploadedFile('one.mp4', MP4),
            'other': SimpleUploadedFile('two.mp4', MP4)}, format='multipart')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Post.objects.exists())

    def test_put_patch_multipart_cannot_bypass_upload_validation(self):
        from rest_framework.views import APIView
        from rest_framework.response import Response
        from django.urls import path

        class UploadEcho(APIView):
            def patch(self, request):
                return Response({'files': list(request.FILES)})
            put = patch
        with override_settings(ROOT_URLCONF=type('Routes', (), {'urlpatterns': [path('upload/', UploadEcho.as_view())]})):
            for method in ['put', 'patch']:
                with self.subTest(method=method):
                    result = getattr(self.api, method)('/upload/', {'video': SimpleUploadedFile('bad.mp4', HTML)}, format='multipart')
                    self.assertEqual(result.status_code, 400)
                    self.assertIn('detail', result.json())

    def test_storage_policy_failure_is_a_controlled_request_error(self):
        from rest_framework.views import APIView
        from rest_framework.response import Response
        from django.urls import path

        class UploadToVideoFolder(APIView):
            def post(self, request):
                LocalPlaybackStorage().save('feed/videos/mismatch.mp3', request.FILES['file'])
                return Response(status=201)
        with override_settings(ROOT_URLCONF=type('Routes', (), {'urlpatterns': [path('upload/', UploadToVideoFolder.as_view())]})):
            result = self.api.post('/upload/', {'file': SimpleUploadedFile('valid.mp3', b'ID3recording')}, format='multipart')
            self.assertEqual(result.status_code, 400)
            self.assertIn('detail', result.json())
            self.assertFalse(list(Path(self.media.name).rglob('*.mp3')))

    def test_existing_html_is_inert_on_all_public_and_private_media_namespaces(self):
        Post.objects.create(author=self.owner, visibility='PUBLIC', video='feed/videos/old.html')
        Message.objects.create(conversation=self.conversation, sender=self.owner, video='messages/videos/old.html')
        for prefix in ['feed/videos/', 'messages/videos/', 'portfolio/files/', 'talents/profile/',
            'organizations/logos/', 'coaches/profiles/', 'events/gallery/', 'athletes/media/']:
            with self.subTest(prefix=prefix):
                name = FileSystemStorage().save(prefix + 'old.html', ContentFile(HTML))
                if prefix.startswith('portfolio/'):
                    self.reference_portfolio(name)
                self.reference_profile_asset(name)
                response = self.api.get('/media/' + name)
                self.assert_inert(response)
                self.assertEqual(b''.join(response.streaming_content), HTML)
                self.assertEqual(Path(self.media.name, name).read_bytes(), HTML)

    def test_legacy_svg_and_html_looking_text_are_downloads(self):
        for name, content in [('portfolio/files/legacy.svg', b'<svg onload="alert(1)"/>'),
                              ('portfolio/files/lesson.txt', HTML)]:
            FileSystemStorage().save(name, ContentFile(content))
            self.reference_portfolio(name)
            response = self.api.get('/media/' + name)
            self.assert_inert(response)
            self.assertEqual(b''.join(response.streaming_content), content)

    def test_range_head_and_debug_false_preserve_legitimate_bytes(self):
        name = FileSystemStorage().save('feed/videos/clip.mp4', ContentFile(MP4))
        Post.objects.create(author=self.owner, visibility='PRIVATE', video=name)
        with override_settings(DEBUG=False):
            ranged = self.api.get('/media/' + name, HTTP_RANGE='bytes=2-9')
            self.assertEqual(ranged.status_code, 206)
            self.assertEqual(ranged['Content-Type'], 'video/mp4')
            self.assertIn('sandbox', ranged['Content-Security-Policy'])
            self.assertEqual(b''.join(ranged.streaming_content), MP4[2:10])
            head = self.api.head('/media/' + name)
            self.assertEqual(head.status_code, 200)
            self.assertEqual(head['Content-Length'], str(len(MP4)))
            self.assertEqual(head.content, b'')
        self.api.force_authenticate(self.other)
        self.assertEqual(self.api.get('/media/' + name).status_code, 404)

    def test_internal_cache_and_unknown_paths_are_not_public_even_in_debug(self):
        for path in ['.playback-cache/secret.mp4', 'private/secret.html', 'feed/videos/../secret.html']:
            with self.subTest(path=path):
                self.assertEqual(self.api.get('/media/' + path).status_code, 404)

    def test_verification_owner_and_reviewer_can_download_but_outsider_cannot(self):
        talent = TalentProfile.objects.create(user=self.owner)
        name = FileSystemStorage().save('verification_documents/old.html', ContentFile(HTML))
        VerificationRequest.objects.create(talent=talent, document=name)
        self.assert_inert(self.api.head('/media/' + name))
        self.api.force_authenticate(self.other)
        self.assertEqual(self.api.get('/media/' + name).status_code, 404)
        self.other.role = 'ADMIN'; self.other.save(update_fields=['role'])
        self.assert_inert(self.api.head('/media/' + name))

    def test_lesson_owner_and_enrollee_keep_legitimate_note_access(self):
        category, _ = LearningCategory.objects.get_or_create(name='Safe category')
        course = Course.objects.create(creator=self.owner, category=category, title='Safe course', slug='safe-course')
        name = FileSystemStorage().save('learning/notes/notes.pdf', ContentFile(PDF))
        Lesson.objects.create(course=course, title='Lesson', notes=name, order=1)
        self.assert_inert(self.api.head('/media/' + name))
        self.api.force_authenticate(self.other)
        self.assertEqual(self.api.get('/media/' + name).status_code, 404)
        Enrollment.objects.create(course=course, user=self.other)
        self.assert_inert(self.api.head('/media/' + name))

    def cloud_remote(self, content_type, status=200):
        remote = Mock(status_code=status)
        remote.headers = {'Content-Type': content_type, 'Content-Length': str(len(HTML)),
            'Content-Disposition': 'inline; filename=evil.html'}
        remote.iter_content.return_value = iter([HTML])
        return remote

    def test_cloud_upstream_html_svg_and_unknown_types_are_never_forwarded_inline(self):
        self.reference_profile_asset('talents/profile/extensionless')
        with override_settings(STORAGES={'default': {'BACKEND': 'config.media_storage.PlaybackMediaStorage'}, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}):
            for mime in ['text/html', 'image/svg+xml', 'text/xml', 'application/x-javascript', 'application/octet-stream']:
                with self.subTest(mime=mime), patch('config.media_views._cloud_url', return_value='https://cloudinary.invalid/asset'), \
                     patch('requests.Session.get', return_value=self.cloud_remote(mime)):
                    response = self.api.get('/media/talents/profile/extensionless')
                    self.assert_inert(response)
                    self.assertEqual(b''.join(response.streaming_content), HTML)

    def test_cloud_safe_extensionless_raster_and_legacy_raw_namespace_fallback(self):
        self.reference_profile_asset('talents/profile/extensionless')
        self.reference_portfolio('portfolio/files/legacy.pdf')
        with override_settings(STORAGES={'default': {'BACKEND': 'config.media_storage.PlaybackMediaStorage'}, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}), \
             patch('config.media_views._cloud_url', return_value='https://cloudinary.invalid/asset'), \
             patch('requests.Session.get', return_value=self.cloud_remote('image/jpeg')):
            response = self.api.get('/media/talents/profile/extensionless')
            self.assertEqual(response['Content-Type'], 'image/jpeg')
            self.assertTrue(response['Content-Disposition'].startswith('inline'))
            response.close()
        with override_settings(STORAGES={'default': {'BACKEND': 'config.media_storage.PlaybackMediaStorage'}, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}), \
             patch('config.media_views._cloud_url', return_value='https://cloudinary.invalid/asset') as cloud_url, \
             patch('requests.Session.get', side_effect=[self.cloud_remote('x', 404), self.cloud_remote('x', 404), self.cloud_remote('application/pdf')]):
            response = self.api.get('/media/portfolio/files/legacy.pdf')
            self.assert_inert(response)
            self.assertEqual(cloud_url.call_args_list[-1].args[2], 'image')
            response.close()

    def test_cloud_head_and_partial_active_content_keep_download_headers(self):
        self.reference_portfolio('portfolio/files/legacy.html')
        with override_settings(STORAGES={'default': {'BACKEND': 'config.media_storage.PlaybackMediaStorage'},
            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}), \
             patch('config.media_views._cloud_url', return_value='https://cloudinary.invalid/asset'):
            with patch('requests.Session.get', return_value=self.cloud_remote('text/html')):
                self.assert_inert(self.api.head('/media/portfolio/files/legacy.html'))
            remote = self.cloud_remote('text/html', 206)
            remote.headers['Content-Range'] = 'bytes 0-9/100'
            with patch('requests.Session.get', return_value=remote):
                response = self.api.get('/media/portfolio/files/legacy.html', HTTP_RANGE='bytes=0-9')
                self.assertEqual(response.status_code, 206)
                self.assertEqual(response['Content-Type'], 'application/octet-stream')
                self.assertTrue(response['Content-Disposition'].startswith('attachment'))
                self.assertIn('sandbox', response['Content-Security-Policy'])
                response.close()

    def test_cloud_transfer_encoding_does_not_corrupt_download_length(self):
        self.reference_portfolio('portfolio/files/legacy.pdf')
        remote = self.cloud_remote('application/pdf')
        remote.headers.update({'Content-Encoding': 'gzip', 'Content-Length': '5'})
        with override_settings(STORAGES={'default': {'BACKEND': 'config.media_storage.PlaybackMediaStorage'},
            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}), \
             patch('config.media_views._cloud_url', return_value='https://cloudinary.invalid/asset'), \
             patch('requests.Session.get', return_value=remote) as fetch:
            response = self.api.get('/media/portfolio/files/legacy.pdf')
            self.assert_inert(response)
            self.assertNotIn('Content-Length', response)
            self.assertNotIn('Content-Encoding', response)
            self.assertEqual(fetch.call_args.kwargs['headers']['Accept-Encoding'], 'identity')
            self.assertEqual(b''.join(response.streaming_content), HTML)

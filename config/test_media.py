import os
import runpy
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from config.media_storage import PlaybackMediaStorage
from feed.models import Post
from feed.serializers import PostSerializer
from messaging.models import Conversation, ConversationParticipant, Message


class CloudMediaTests(SimpleTestCase):
    @patch('cloudinary.uploader.upload')
    def test_upload_resource_type_and_existing_names(self, upload):
        storage = PlaybackMediaStorage()
        for folder, kind in [('messages/audio', 'video'), ('messages/videos', 'video'),
                             ('feed/videos', 'video'), ('feed/images', 'image')]:
            with self.subTest(folder=folder):
                upload.return_value = {'public_id': f'{folder}/original_id'}
                self.assertEqual(storage.save(f'{folder}/clip.webm', ContentFile(b'original')),
                                 f'{folder}/original_id')
                self.assertEqual(upload.call_args.kwargs['resource_type'], kind)
                self.assertTrue(upload.call_args.kwargs['folder'].endswith(folder))
                if folder.startswith(('messages/', 'feed/')):
                    self.assertEqual(upload.call_args.kwargs['type'], 'authenticated')
                else:
                    self.assertNotIn('type', upload.call_args.kwargs)

    @patch('cloudinary.uploader.destroy', return_value={'result': 'ok'})
    def test_delete_uses_same_video_namespace(self, destroy):
        PlaybackMediaStorage().delete('messages/audio/existing_id')
        self.assertEqual(destroy.call_args.kwargs['resource_type'], 'video')

    def test_delivery_codecs_and_local_legacy_file(self):
        import cloudinary
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory), patch.dict(cloudinary.config().__dict__, {'cloud_name': 'media-tests', 'secure': True}):
            storage = PlaybackMediaStorage()
            audio = storage.url('messages/audio/existing_id')
            video = storage.url('feed/videos/existing_id')
            self.assertEqual(audio, '/media/messages/audio/existing_id?playback=mp3')
            self.assertEqual(video, '/media/feed/videos/existing_id?playback=mp4')
            prefixed = storage.url('media/messages/audio/existing_id')
            self.assertEqual(prefixed, '/media/messages/audio/existing_id?playback=mp3')
            local = FileSystemStorage()
            name = local.save('messages/audio/legacy.webm', ContentFile(b'unchanged'))
            self.assertEqual(storage.url(name), '/media/messages/audio/legacy.webm?playback=mp3')
            with local.open(name) as original:
                self.assertEqual(original.read(), b'unchanged')

    def test_private_cloud_urls_are_application_routes_and_public_profile_media_stays_public(self):
        import cloudinary
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory), patch.dict(cloudinary.config().__dict__, {'cloud_name': 'media-tests', 'secure': True}):
            storage = PlaybackMediaStorage()
            self.assertEqual(storage.url('feed/images/private'), '/media/feed/images/private')
            self.assertEqual(storage.url('messages/files/private.pdf'), '/media/messages/files/private.pdf')
            self.assertTrue(storage.url('talents/profile/public.jpg').startswith('https://'))

    def test_railway_and_local_storage_selection(self):
        for cloud in (False, True):
            environment = {'RAILWAY_ENVIRONMENT_NAME': 'production', 'SECRET_KEY': 'fixture-only-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ-abcdefgh'}
            if cloud:
                environment.update(CLOUDINARY_CLOUD_NAME='test', CLOUDINARY_API_KEY='key', CLOUDINARY_API_SECRET='secret')
            with patch.dict(os.environ, environment, clear=True), patch('dotenv.load_dotenv'):
                configured = runpy.run_path(str(Path(__file__).with_name('settings.py')))
            self.assertFalse(configured['DEBUG'])
            self.assertEqual(configured['STORAGES']['default']['BACKEND'],
                             'config.media_storage.PlaybackMediaStorage' if cloud else 'config.media_storage.LocalPlaybackStorage')

    def test_railway_cloudinary_url(self):
        with patch.dict(os.environ, {'RAILWAY_ENVIRONMENT_NAME': 'production', 'SECRET_KEY': 'fixture-only-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ-abcdefgh', 'CLOUDINARY_URL': 'cloudinary://key:secret@media-test'}, clear=True), patch('dotenv.load_dotenv'):
            configured = runpy.run_path(str(Path(__file__).with_name('settings.py')))
        self.assertEqual(configured['CLOUDINARY_CLOUD_NAME'], 'media-test')
        self.assertEqual(configured['STORAGES']['default']['BACKEND'], 'config.media_storage.PlaybackMediaStorage')


@override_settings(STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}},
                   SECURE_SSL_REDIRECT=False)
class LocalPlaybackTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=self.directory.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.user = get_user_model().objects.create_user(username='media-owner')
        self.other = get_user_model().objects.create_user(username='media-outsider')
        self.conversation = Conversation.objects.create(created_by=self.user)
        ConversationParticipant.objects.create(conversation=self.conversation, user=self.user)
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def upload_audio(self):
        response = self.api.post(f'/api/messaging/conversations/{self.conversation.pk}/messages/create/',
                                 {'message_type': 'AUDIO', 'audio': SimpleUploadedFile('voice.webm', b'0123456789', 'audio/webm')}, format='multipart')
        self.assertEqual(response.status_code, 201, response.data)
        message = Message.objects.get(pk=response.data['id'])
        with message.audio.open() as original:
            self.assertEqual(original.read(), b'0123456789')
        self.assertTrue(response.data['audio'].startswith('http://testserver/media/'))
        return message.audio.url

    def test_audio_upload_and_seek_under_debug_false(self):
        url = self.upload_audio()
        with override_settings(DEBUG=False):
            response = self.api.get(url, HTTP_RANGE='bytes=2-5')
            self.assertEqual(response.status_code, 206)
            self.assertEqual(response['Content-Type'], 'audio/webm')
            self.assertEqual(response['Content-Range'], 'bytes 2-5/10')
            self.assertEqual(b''.join(response.streaming_content), b'2345')
            head = self.api.head(url)
            self.assertEqual(head.status_code, 200)
            self.assertEqual(head['Content-Length'], '10')
            self.assertEqual(head.content, b'')

    def test_ranges_and_unauthorized_access(self):
        url = self.upload_audio()
        response = self.api.get(url, HTTP_RANGE='bytes=-3')
        self.assertEqual(b''.join(response.streaming_content), b'789')
        for invalid in ('bytes=99-', 'bytes=5-2', 'bytes=-0', 'bytes=0-1,3-4', 'bytes=-'):
            self.assertEqual(self.api.get(url, HTTP_RANGE=invalid).status_code, 416)
        self.api.force_authenticate(self.other)
        self.assertEqual(self.api.get(url).status_code, 404)
        self.api.force_authenticate(None)
        self.assertEqual(self.api.get(url).status_code, 404)

    def test_feed_upload_serializer_and_private_video_permissions(self):
        from types import SimpleNamespace
        serializer = PostSerializer(data={'caption': 'video', 'video': SimpleUploadedFile('clip.mp4', b'original-video', 'video/mp4')}, context={'request': SimpleNamespace(user=self.user)})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        post = serializer.save(author=self.user, visibility='PRIVATE')
        url = post.video.url
        response = self.api.get(url)
        self.assertEqual(response['Content-Type'], 'video/mp4')
        self.assertEqual(b''.join(response.streaming_content), b'original-video')
        self.api.force_authenticate(self.other)
        self.assertEqual(self.api.get(url).status_code, 404)
        post.visibility = 'PUBLIC'
        post.save(update_fields=['visibility'])
        self.assertEqual(self.api.head(url).status_code, 200)

    def test_private_post_image_uses_post_visibility_for_streaming(self):
        post = Post.objects.create(author=self.user, visibility='PRIVATE',
            image=SimpleUploadedFile('private.jpg', b'private-image', 'image/jpeg'))
        url = post.image.url
        owner_response = self.api.get(url)
        self.assertEqual(owner_response.status_code, 200)
        self.assertEqual(b''.join(owner_response.streaming_content), b'private-image')
        owner_response.close()
        self.api.force_authenticate(self.other)
        self.assertEqual(self.api.get(url).status_code, 404)
        self.api.force_authenticate(None)
        self.assertIn(self.api.get(url).status_code, (401, 403, 404))
        post.visibility = 'PUBLIC'
        post.save(update_fields=['visibility'])
        public_response = self.api.get(url)
        self.assertEqual(public_response.status_code, 200)
        self.assertEqual(b''.join(public_response.streaming_content), b'private-image')
        public_response.close()

    def test_private_cloudinary_asset_is_streamed_only_after_database_acl(self):
        from config.media_views import _cloud_url
        post = Post.objects.create(author=self.user, visibility='PRIVATE', image='feed/images/private-cloud')
        remote = type('RemoteResponse', (), {
            'status_code': 200,
            'headers': {'Content-Type': 'image/jpeg', 'Content-Length': '12'},
            'iter_content': lambda self, chunk_size: iter([b'private-cloud']),
            'close': lambda self: None,
        })()
        settings_override = override_settings(STORAGES={
            'default': {'BACKEND': 'config.media_storage.PlaybackMediaStorage'},
            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
        })
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        with patch('config.media_views._cloud_url', return_value='https://cloudinary.invalid/private-signature') as signed_url, \
             patch('requests.Session.get', return_value=remote) as fetch:
            response = self.api.get('/media/feed/images/private-cloud')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b''.join(response.streaming_content), b'private-cloud')
            self.assertEqual(signed_url.call_args.kwargs['authenticated'], True)
            self.assertNotIn('cloudinary.invalid', response.get('Location', ''))
            self.api.force_authenticate(self.other)
            self.assertEqual(self.api.get('/media/feed/images/private-cloud').status_code, 404)
            self.assertEqual(fetch.call_count, 1)

    def test_jwt_media_auth_and_absolute_message_list_urls(self):
        from rest_framework_simplejwt.tokens import AccessToken
        url = self.upload_audio()
        self.api.force_authenticate(None)
        self.api.credentials(HTTP_AUTHORIZATION=f'Bearer {AccessToken.for_user(self.user)}')
        self.assertEqual(self.api.head(url).status_code, 200)
        response = self.api.get(f'/api/messaging/conversations/{self.conversation.pk}/messages/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data[0]['audio'].startswith('http://testserver/media/'))

    def test_real_local_voice_conversion_caches_and_preserves_original(self):
        import io
        import wave
        from config.media_storage import LocalPlaybackStorage
        from config.media_transcoding import playback_copy
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(8000)
            wav.writeframes(b'\0\0' * 4000)
        original = buffer.getvalue()
        message = Message.objects.create(conversation=self.conversation, sender=self.user,
                                         message_type='AUDIO', audio=SimpleUploadedFile('voice.wav', original, 'audio/wav'))
        url = LocalPlaybackStorage().url(message.audio.name)
        response = self.api.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'audio/mpeg')
        converted = b''.join(response.streaming_content)
        self.assertGreater(len(converted), 100)
        with message.audio.open() as uploaded:
            self.assertEqual(uploaded.read(), original)
        with patch('config.media_transcoding.subprocess.run', side_effect=AssertionError('cache should be reused')):
            cached = playback_copy(message.audio.path, 'mp3')
            self.assertEqual(cached.read_bytes(), converted)
        seek = self.api.get(url, HTTP_RANGE='bytes=0-9')
        self.assertEqual(seek.status_code, 206)
        self.assertEqual(b''.join(seek.streaming_content), converted[:10])

    def test_real_local_video_converts_to_h264_aac_and_preserves_original(self):
        import subprocess
        from imageio_ffmpeg import get_ffmpeg_exe
        from config.media_storage import LocalPlaybackStorage
        source = Path(self.directory.name) / 'fixture.webm'
        subprocess.run([get_ffmpeg_exe(), '-nostdin', '-hide_banner', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'color=c=blue:s=64x64:d=0.4',
                        '-f', 'lavfi', '-i', 'sine=frequency=440:duration=0.4',
                        '-c:v', 'libvpx', '-c:a', 'libopus', '-shortest', str(source)],
                       check=True, capture_output=True, timeout=20)
        original = source.read_bytes()
        post = Post.objects.create(author=self.user, video=SimpleUploadedFile('fixture.webm', original, 'video/webm'))
        response = self.api.get(LocalPlaybackStorage().url(post.video.name))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'video/mp4')
        converted = b''.join(response.streaming_content)
        destination = Path(self.directory.name) / 'result.mp4'
        destination.write_bytes(converted)
        probe = subprocess.run([get_ffmpeg_exe(), '-hide_banner', '-i', str(destination)], capture_output=True, timeout=20)
        metadata = probe.stderr.decode(errors='replace')
        self.assertIn('Video: h264', metadata)
        self.assertIn('Audio: aac', metadata)
        with post.video.open() as uploaded:
            self.assertEqual(uploaded.read(), original)

    def test_invalid_local_media_does_not_remove_original(self):
        url = self.upload_audio()
        self.assertEqual(self.api.get(url + '?playback=mp3').status_code, 422)
        raw = self.api.get(url)
        self.assertEqual(b''.join(raw.streaming_content), b'0123456789')
        self.assertEqual(self.api.get(url + '?playback=mp4').status_code, 400)

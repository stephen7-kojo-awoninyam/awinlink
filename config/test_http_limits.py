import asyncio
import tempfile
from unittest.mock import patch

from asgiref.sync import async_to_sync
from asgiref.testing import ApplicationCommunicator
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import RequestAborted
from django.core.handlers.asgi import ASGIHandler
from django.http import HttpResponse
from django.test import SimpleTestCase, TestCase, TransactionTestCase, RequestFactory, override_settings
from rest_framework.test import APIClient

from .http_limits import HTTPBodyLimits
from .resource_limits import Lease, ResourceLimited, ResourceUnavailable
from .upload_handlers import SecureUploadHandler, UploadSecurityMiddleware


class HTTPIngressTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        limits = {**settings.AWINLINK_RESOURCE_LIMITS, 'upload_global': (1, 3)}
        override = override_settings(AWINLINK_RESOURCE_CACHE_ALIAS='default', AWINLINK_ENV='development',
            AWINLINK_RESOURCE_LIMITS=limits, AWINLINK_JSON_BODY_BYTES=20,
            AWINLINK_UPLOAD_TOTAL_BYTES=20, AWINLINK_UPLOAD_OVERHEAD_BYTES=10)
        override.enable(); self.addCleanup(override.disable)

    async def django_reader(self, scope, receive, send):
        try:
            body = await ASGIHandler().read_body(receive)
        except RequestAborted:
            return
        try:
            payload = body.read()
        finally:
            body.close()
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': payload})

    def socket(self, content_type='multipart/form-data; boundary=fixture', extra=(), reader=None):
        return ApplicationCommunicator(HTTPBodyLimits(reader or self.django_reader), {
            'type': 'http', 'http_version': '1.1', 'method': 'POST', 'path': '/api/fixture/',
            'headers': [(b'content-type', content_type.encode()), *extra],
        })

    async def status(self, socket):
        response = await socket.receive_output(timeout=5)
        await socket.receive_output(timeout=5)
        await socket.wait(timeout=5)
        return response['status']

    def test_unknown_or_understated_length_counts_actual_chunks_and_closes_django_spool(self):
        files = []
        original = tempfile.SpooledTemporaryFile
        def record(*args, **kwargs):
            file = original(*args, **kwargs); files.append(file); return file
        async def run():
            for headers in ((), ((b'content-length', b'1'),)):
                socket = self.socket(extra=headers)
                await socket.send_input({'type': 'http.request', 'body': b'x' * 16, 'more_body': True})
                await socket.send_input({'type': 'http.request', 'body': b'x' * 16, 'more_body': False})
                self.assertEqual(await self.status(socket), 413)
            self.assertTrue(files and all(file.closed for file in files))
        with patch('django.core.handlers.asgi.tempfile.SpooledTemporaryFile', record):
            async_to_sync(run)()

    def test_declared_oversized_and_malformed_lengths_are_rejected_before_buffer_creation(self):
        async def run():
            for length, status in ((b'31', 413), (b'-1', 400), (b'invalid', 400)):
                socket = self.socket(extra=((b'content-length', length),))
                self.assertEqual(await self.status(socket), status)
        with patch('django.core.handlers.asgi.tempfile.SpooledTemporaryFile', side_effect=AssertionError('No spool should be created')):
            async_to_sync(run)()

    def test_json_is_bounded_and_read_only_requests_do_not_require_redis(self):
        async def run():
            socket = self.socket('application/json')
            await socket.send_input({'type': 'http.request', 'body': b'x' * 21})
            self.assertEqual(await self.status(socket), 413)
            with patch('config.http_limits.Lease', side_effect=ResourceUnavailable()):
                socket = self.socket('application/json')
                await socket.send_input({'type': 'http.request', 'body': b'{}'})
                self.assertEqual(await self.status(socket), 200)
        async_to_sync(run)()

    def test_global_admission_precedes_body_buffering_and_disconnect_frees_capacity(self):
        async def run():
            began = asyncio.Event()
            async def reader(*args):
                began.set()
                await self.django_reader(*args)
            first = self.socket(reader=reader)
            await first.send_input({'type': 'http.request', 'body': b'partial', 'more_body': True})
            await asyncio.wait_for(began.wait(), timeout=5)
            second = self.socket()
            self.assertEqual(await self.status(second), 429)
            await first.send_input({'type': 'http.disconnect'})
            await first.wait(timeout=5)
            third = self.socket()
            await third.send_input({'type': 'http.request', 'body': b'valid'})
            self.assertEqual(await self.status(third), 200)
        async_to_sync(run)()

    @override_settings(AWINLINK_UPLOAD_IDLE_SECONDS=.1, AWINLINK_UPLOAD_REQUEST_SECONDS=1)
    def test_stalled_upload_closes_its_spool_and_releases_admission(self):
        async def run():
            socket = self.socket()
            await socket.send_input({'type': 'http.request', 'body': b'x', 'more_body': True})
            self.assertEqual(await self.status(socket), 408)
            replacement = self.socket()
            await replacement.send_input({'type': 'http.request', 'body': b'valid'})
            self.assertEqual(await self.status(replacement), 200)
        async_to_sync(run)()

    def test_upload_handler_borrows_ingress_lease_without_double_admission_or_early_release(self):
        lease = Lease('upload_global', 'cluster').acquire()
        self.addCleanup(lease.release)
        request = RequestFactory().post('/api/fixture/', b'', content_type='application/octet-stream')
        request.session = {}
        request.scope = {'_awinlink_upload_global_lease': lease}
        handler = SecureUploadHandler(request); request.upload_handlers = [handler]
        handler.new_file('file', 'notes.txt', 'text/plain', 4, None, None)
        handler.receive_data_chunk(b'note', 0); handler.file_complete(4)
        UploadSecurityMiddleware(lambda request: HttpResponse()).process_response(request, HttpResponse())
        self.assertIs(handler.global_lease, lease)
        with self.assertRaises(ResourceLimited): Lease('upload_global', 'cluster').acquire()


class JSONBodyBudgetTests(TestCase):
    @override_settings(AWINLINK_JSON_BODY_BYTES=16)
    def test_wsgi_rejects_oversized_json_before_authentication_or_view_work(self):
        response = APIClient().post('/api/auth/login/', {'username': 'x' * 100, 'password': 'fixture'}, format='json')
        self.assertEqual(response.status_code, 413)
        self.assertIn('no-store', response['Cache-Control'])


@override_settings(ALLOWED_HOSTS=['testserver'], SECURE_SSL_REDIRECT=False)
class ASGIUploadWorkflowTests(TransactionTestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from rest_framework_simplejwt.tokens import AccessToken
        cache.clear()
        self.user = get_user_model().objects.create_user('asgi-upload-owner')
        self.token = str(AccessToken.for_user(self.user))
        self.mp4 = b'\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isommp42' + b'\x00' * 16

    def upload(self, token=None, filename='clip.mp4', content=None, cookie=None):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test.client import encode_multipart, BOUNDARY, MULTIPART_CONTENT
        from config.asgi import application
        body = encode_multipart(BOUNDARY, {'caption': 'Preserved native upload',
            'video': SimpleUploadedFile(filename, self.mp4 if content is None else content, 'video/mp4')})
        async def run():
            headers = [(b'host', b'testserver'), (b'content-type', MULTIPART_CONTENT.encode())]
            if token is not None:
                headers.append((b'authorization', ('Bearer ' + token).encode()))
            if cookie is not None:
                headers.append((b'cookie', cookie.encode()))
            socket = ApplicationCommunicator(application, {'type': 'http', 'http_version': '1.1',
                'method': 'POST', 'path': '/api/feed/posts/create/', 'query_string': b'', 'scheme': 'http',
                'server': ('testserver', 80), 'client': ('127.0.0.1', 1234),
                'headers': headers})
            await socket.send_input({'type': 'http.request', 'body': body[:30], 'more_body': True})
            await socket.send_input({'type': 'http.request', 'body': body[30:]})
            response = await socket.receive_output(timeout=5)
            while (await socket.receive_output(timeout=5)).get('more_body', False): pass
            await socket.wait(timeout=5)
            # HTTP header names are case-insensitive; Django retains display case.
            response['headers'] = [(name.lower(), value) for name, value in response['headers']]
            return response
        return async_to_sync(run)()

    def test_asgi_worker_sees_migrated_schema_and_committed_user(self):
        from channels.db import database_sync_to_async
        from django.contrib.auth import get_user_model
        # Force an independent worker connection rather than querying in the
        # main test thread. This detects mismatched in-memory DB setup directly.
        exists = database_sync_to_async(
            lambda: get_user_model().objects.filter(pk=self.user.pk).exists(), thread_sensitive=False)
        self.assertTrue(async_to_sync(exists)())

    def test_unknown_length_native_upload_uses_one_shared_slot_and_preserves_file(self):
        from feed.models import Post
        limits = {**settings.AWINLINK_RESOURCE_LIMITS, 'upload_global': (1, 120)}
        with override_settings(AWINLINK_RESOURCE_LIMITS=limits):
            self.assertEqual(self.upload(self.token)['status'], 201)
            lease = Lease('upload_global', 'cluster').acquire(); lease.release()
        post = Post.objects.get(author=self.user)
        with post.video.open('rb') as file:
            self.assertEqual(file.read(), self.mp4)

    def test_chunked_upload_preserves_authentication_and_releases_capacity_on_denial(self):
        from feed.models import Post
        limits = {**settings.AWINLINK_RESOURCE_LIMITS, 'upload_global': (1, 120)}
        with override_settings(AWINLINK_RESOURCE_LIMITS=limits):
            for token in (None, 'invalid-token'):
                with self.subTest(authenticated=token is not None):
                    self.assertEqual(self.upload(token)['status'], 401)
                    lease = Lease('upload_global', 'cluster').acquire(); lease.release()
        self.assertFalse(Post.objects.filter(author=self.user).exists())

    def test_chunked_upload_rejects_active_files_and_invalid_video_signatures(self):
        from feed.models import Post
        for filename, content in [('clip.svg', b'<svg/>'), ('clip.mp4', b'not a video')]:
            with self.subTest(filename=filename):
                response = self.upload(self.token, filename, content)
                self.assertEqual(response['status'], 400)
                self.assertIn(b'no-store', dict(response['headers'])[b'cache-control'])
        self.assertFalse(Post.objects.filter(author=self.user).exists())

    def test_chunked_session_upload_still_requires_csrf(self):
        from feed.models import Post
        self.client.force_login(self.user)
        cookie = f'{settings.SESSION_COOKIE_NAME}={self.client.cookies[settings.SESSION_COOKIE_NAME].value}'
        self.assertEqual(self.upload(cookie=cookie)['status'], 403)
        self.assertFalse(Post.objects.filter(author=self.user).exists())

    @override_settings(AWINLINK_UPLOAD_TOTAL_BYTES=16, AWINLINK_UPLOAD_OVERHEAD_BYTES=1)
    def test_chunked_upload_body_limit_is_enforced_before_authentication(self):
        with patch('config.upload_handlers.SecureUploadHandler.new_file', side_effect=AssertionError('No parsing permitted')):
            self.assertEqual(self.upload(self.token)['status'], 413)

    def test_chunked_upload_keeps_shared_byte_quota_enforcement(self):
        from feed.models import Post
        limits = {**settings.AWINLINK_RESOURCE_LIMITS, 'upload_bytes': (1, 3600)}
        with override_settings(AWINLINK_RESOURCE_LIMITS=limits):
            response = self.upload(self.token)
        self.assertEqual(response['status'], 429)
        self.assertTrue(any(key == b'retry-after' for key, _ in response['headers']))
        self.assertFalse(Post.objects.filter(author=self.user).exists())

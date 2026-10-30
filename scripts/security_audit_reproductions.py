"""Audit-only characterization of OPEN findings; these are not security acceptance tests.

Run with scripts/test_security_phase1.py scripts.security_audit_reproductions --fast.
Assertions deliberately document vulnerable behavior. Reverse the affected assertions
when implementing fixes, and move them to the owning app's regression suite.
S01 was fixed and its acceptance tests now live in accounts.test_role_security.
S02/S04 upload controls are covered by config.test_upload_security.
S03 acceptance tests now live in portfolio.test_permissions.
S05-S08 acceptance tests live in talents.test_profile_privacy and events.test_privacy,
with linked-feed and recommendation regressions in their owning apps.
S10/S11 acceptance tests live in accounts.test_admin_login and config.test_production_security.
"""
from datetime import date
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User, UserBlock
from athletes.models import AthleteProfile
from coaches.models import CoachProfile
from portfolio.models import PortfolioItem
from scouts.models import ScoutProfile
from talents.models import TalentProfile


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class OpenSecurityFindingReproductions(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('audit-owner', email='private-login@example.invalid')
        self.viewer = User.objects.create_user('audit-viewer')
        self.talent = TalentProfile.objects.create(user=self.owner, profile_visibility='PRIVATE')
        self.item = PortfolioItem.objects.create(talent=self.talent, title='Private project marker',
                                                 item_type='DOCUMENT', description='Private description marker')
        self.api = APIClient()
        self.api.force_authenticate(self.viewer)

    def assert_main_denies(self):
        self.assertEqual(self.api.get(f'/api/talents/{self.talent.pk}/').status_code, 404)






    def test_account_deletion_leaves_uploaded_document_in_storage(self):
        self.owner.set_password('audit-fixture-password')
        self.owner.save(update_fields=['password'])
        self.api.force_authenticate(self.owner)
        with tempfile.TemporaryDirectory(prefix='awinlink-security-erasure-') as media:
            with override_settings(MEDIA_ROOT=media, STORAGES={
                'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
            }):
                self.item.file.save('audit-document.pdf', SimpleUploadedFile('audit-document.pdf', b'audit fixture'))
                storage, name = self.item.file.storage, self.item.file.name
                response = self.api.delete('/api/auth/account/', {'password': 'audit-fixture-password'}, format='json')
                self.assertEqual(response.status_code, 204, response.data)
                self.assertFalse(User.objects.filter(pk=self.owner.pk).exists())
                self.assertTrue(storage.exists(name))





@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
    ALLOWED_HOSTS=['testserver'], MESSAGING_WS_HEARTBEAT_SECONDS=0.05,
    CHANNEL_LAYERS={'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}})
class SocketExpiryAuditControl(TransactionTestCase):
    def test_successfully_connected_socket_closes_at_credential_expiry(self):
        # Load ASGI before minting a short-lived token; avoid timing the imports.
        from config.asgi import application
        from datetime import timedelta
        from asgiref.sync import async_to_sync
        from channels.testing import WebsocketCommunicator
        from rest_framework_simplejwt.tokens import AccessToken
        user = User.objects.create_user('audit-socket-expiry')
        token = AccessToken.for_user(user)
        token.set_exp(lifetime=timedelta(seconds=5))

        async def verify():
            socket = WebsocketCommunicator(application, '/ws/user/', headers=[
                (b'authorization', ('Bearer ' + str(token)).encode()),
            ])
            self.assertTrue((await socket.connect(timeout=3))[0])
            await socket.receive_json_from(timeout=3)
            self.assertEqual((await socket.receive_output(timeout=7))['code'], 4001)
            await socket.disconnect()
        async_to_sync(verify)()

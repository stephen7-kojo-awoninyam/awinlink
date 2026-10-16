from unittest.mock import patch
from uuid import uuid4

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from . import classroom_chat as chat, classroom_services as services
from . import test_ui as ui
from .models import ClassroomChatMessage, Enrollment
from .test_classroom_security import ClassroomFixture


class ChatFixture(ClassroomFixture):
    def setUp(self):
        delivery = patch('notifications.signals.publish_notification')
        delivery.start(); self.addCleanup(delivery.stop)
        super().setUp()
        self.learner_participant = self.admit()

    def send(self, user=None, text='Hello', client_id=None):
        return chat.send(actor=user or self.learner, session_id=self.session.pk,
            data={'client_id': str(client_id or uuid4()), 'text': text})


@override_settings(TEMPLATES=ui.UI_TEMPLATES, STORAGES=ui.UI_STORAGE)
class ClassroomInterfaceSecurityTests(ChatFixture, TestCase):
    def test_browser_login_and_discovery_scope(self):
        url = reverse('learning_classroom', args=[self.session.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.learner)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        for token in ['vc-grid', 'vc-board', 'vc-chat', 'vc-join', 'vc-microphone', 'vc-share', 'csrfmiddlewaretoken']:
            self.assertContains(response, token)
        self.assertEqual(self.client.get(reverse('learning_classrooms')).status_code, 200)

    def test_capabilities_are_server_scoped_and_do_not_grant_learner_staff_actions(self):
        client = APIClient(); url = f'/api/learning/sessions/{self.session.pk}/'
        for user, expected in [(self.learner, False), (self.host, True), (self.cohost, True)]:
            client.force_authenticate(user=user)
            capabilities = client.get(url).data['capabilities']
            self.assertEqual(capabilities['participants'], expected)
            self.assertEqual(capabilities['end'], user.pk == self.host.pk)
        client.force_authenticate(user=self.learner)
        self.assertEqual(client.post(url + 'end/', {}, format='json').status_code, 403)

    def test_chat_admission_enrollment_revocation_and_ended_readonly(self):
        for user in [self.other, self.admin]:
            with self.assertRaises(PermissionDenied): self.send(user)
            with self.assertRaises(PermissionDenied): chat.history(actor=user, session_id=self.session.pk)
        self.send()
        services.end_session(actor=self.host, session=self.session)
        self.assertEqual(len(chat.history(actor=self.learner, session_id=self.session.pk)), 1)
        with self.assertRaises(PermissionDenied): self.send()
        Enrollment.objects.filter(user=self.learner).delete()
        with self.assertRaises(PermissionDenied): chat.history(actor=self.learner, session_id=self.session.pk)

    def test_retry_binding_validation_plain_text_and_bulk_integrity(self):
        client_id = uuid4(); first = self.send(client_id=client_id)
        self.assertEqual(self.send(client_id=client_id)['id'], first['id'])
        with self.assertRaises(PermissionDenied): self.send(self.host, client_id=client_id)
        with self.assertRaises(PermissionDenied): self.send(text='Changed', client_id=client_id)
        for text in ['', 'x' * 2001, '\x00bad', {'html': 'bad'}]:
            with self.assertRaises(ValidationError): self.send(text=text)
        with self.assertRaises(ValidationError): ClassroomChatMessage.objects.update(text='overwritten')
        data = {'client_id': str(uuid4()), 'text': 'hello', 'sender_id': self.admin.pk}
        with self.assertRaises(ValidationError): chat.send(actor=self.learner, session_id=self.session.pk, data=data)
        message = self.send(text='<script>window.injected=true</script>')
        self.assertEqual(message['text'], '<script>window.injected=true</script>')  # Clients render as text, never HTML.

    def test_chat_api_auth_csrf_and_cross_session_isolation(self):
        url = f'/api/learning/sessions/{self.session.pk}/chat/'
        client = APIClient(enforce_csrf_checks=True)
        self.assertIn(client.get(url).status_code, [401, 403])
        client.force_login(self.learner)
        self.assertEqual(client.post(url, {'client_id': str(uuid4()), 'text': 'Hi'}, format='json').status_code, 403)
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {AccessToken.for_user(self.learner)}')
        self.assertEqual(client.post(url, {'client_id': str(uuid4()), 'text': 'Hi'}, format='json').status_code, 201)
        self.assertEqual(client.get(url).data['results'][0]['sender_id'], self.learner.pk)
        other = self.schedule()
        services.start_session(actor=self.host, session=other)
        self.assertEqual(client.get(f'/api/learning/sessions/{other.pk}/chat/').status_code, 403)
        services.remove_participant(actor=self.host, session=self.session, participant=self.learner_participant)
        self.assertEqual(client.get(url).status_code, 403)


@override_settings(ALLOWED_HOSTS=['testserver'], CHANNEL_LAYERS={'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}, CLASSROOM_WS_HEARTBEAT_SECONDS=.05)
class ClassroomChatSocketTests(ChatFixture, TransactionTestCase):
    def socket(self, user, session=None):
        from config.asgi import application
        return WebsocketCommunicator(application, f'/ws/learning/sessions/{(session or self.session).pk}/whiteboard/',
            headers=[(b'authorization', f'Bearer {AccessToken.for_user(user)}'.encode())])

    def test_live_chat_is_scoped_persisted_and_recovered_after_reconnect(self):
        other = self.schedule(); services.start_session(actor=self.host, session=other)
        async def run():
            host = self.socket(self.host); learner = self.socket(self.learner); unrelated = self.socket(self.host, other)
            for socket in [host, learner, unrelated]:
                self.assertTrue((await socket.connect())[0]); await socket.receive_json_from()
            await host.send_json_to({'type': 'chat', 'client_id': str(uuid4()), 'text': 'Hello class'})
            received = await learner.receive_json_from()
            self.assertEqual(received['type'], 'chat'); self.assertEqual(received['message']['text'], 'Hello class')
            self.assertTrue(await unrelated.receive_nothing(timeout=.1))
            await learner.disconnect()
            learner = self.socket(self.learner); self.assertTrue((await learner.connect())[0]); await learner.receive_json_from()
            await learner.send_json_to({'type': 'chat_history'})
            self.assertEqual((await learner.receive_json_from())['messages'][0]['text'], 'Hello class')
            await learner.send_json_to({'type': 'chat', 'client_id': str(uuid4()), 'text': 'bad', 'sender_id': self.host.pk})
            self.assertEqual((await learner.receive_json_from())['code'], 'invalid_request')
            await database_sync_to_async(services.remove_participant)(actor=self.host, session=self.session, participant=self.learner_participant)
            self.assertEqual((await learner.receive_output())['code'], 4403)
            await host.disconnect(); await learner.disconnect(); await unrelated.disconnect()
        async_to_sync(run)()

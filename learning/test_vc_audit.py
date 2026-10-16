"""Audit regressions: pathological input, lost broadcasts and durable chat catchup."""
from unittest.mock import patch
from uuid import uuid4
import json

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from . import classroom_chat as chat
from . import test_classroom_interfaces as interfaces
from . import test_whiteboard as boards


class VCInputAuditTests(boards.BoardFixture, TestCase):
    def test_huge_integer_coordinate_returns_400_without_mutating_board(self):
        client = APIClient(); client.force_authenticate(user=self.host)
        data = self.data(payload={**boards.drawing(), "x": 10 ** 400})
        response = client.post(f'/api/learning/sessions/{self.session.pk}/whiteboard/', data, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.state()['revision'], 0)

    def test_chat_lone_unicode_surrogate_is_rejected_before_database_encoding(self):
        client = APIClient(); client.force_authenticate(user=self.learner)
        response = client.generic('POST', f'/api/learning/sessions/{self.session.pk}/chat/',
            json.dumps({'client_id': str(uuid4()), 'text': '\ud800'}).encode(), content_type='application/json')
        self.assertEqual(response.status_code, 400)


@override_settings(ALLOWED_HOSTS=['testserver'], CHANNEL_LAYERS={'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}, CLASSROOM_WS_HEARTBEAT_SECONDS=.05)
class VCChatRecoveryAuditTests(interfaces.ChatFixture, TransactionTestCase):
    def test_lost_redis_notification_is_recovered_without_reconnecting_video(self):
        from config.asgi import application
        async def run():
            socket = WebsocketCommunicator(application, f'/ws/learning/sessions/{self.session.pk}/whiteboard/',
                headers=[(b'authorization', f'Bearer {AccessToken.for_user(self.learner)}'.encode())])
            self.assertTrue((await socket.connect())[0]); await socket.receive_json_from()
            await socket.send_json_to({'type': 'chat_history'}); await socket.receive_json_from()
            def lost_publish():
                with patch('learning.classroom_chat.get_channel_layer', return_value=None):
                    return chat.send(actor=self.host, session_id=self.session.pk, data={'client_id': str(uuid4()), 'text': 'Recover me'})
            message = await database_sync_to_async(lost_publish)()
            received = await socket.receive_json_from(timeout=1)
            self.assertIn(message['id'], [item['id'] for item in received['messages']])
            await socket.disconnect()
        async_to_sync(run)()

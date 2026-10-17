import time
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from .models import MobilePushToken, VoipPushToken
from .voip import native_call_uuid, send_voip_call_push


class VoipTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='voip-owner')
        self.other = get_user_model().objects.create_user(username='voip-other')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.token = 'ab' * 32

    def test_registration_validates_and_rebinds_device_ownership(self):
        endpoint = '/api/notifications/voip-push/'
        self.assertEqual(self.client.post(endpoint, {'token': 'bad', 'environment': 'production'}, format='json').status_code, 400)
        body = {'token': self.token, 'environment': 'production', 'expo_token': 'ExpoPushToken[test]'}
        self.assertEqual(self.client.post(endpoint, body, format='json').status_code, 400)
        MobilePushToken.objects.create(user=self.user, token=body['expo_token'], platform='ios')
        self.assertEqual(self.client.post(endpoint, body, format='json').status_code, 201)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.delete(endpoint, {'token': self.token}, format='json').status_code, 204)
        self.assertTrue(VoipPushToken.objects.filter(user=self.user).exists())
        body['expo_token'] = ''
        self.assertEqual(self.client.post(endpoint, body, format='json').status_code, 201)
        self.assertEqual(VoipPushToken.objects.get().user, self.other)
        self.client.delete(endpoint, {'token': self.token}, format='json')
        self.assertFalse(VoipPushToken.objects.exists())

    def test_uuid_matches_native_codec_and_rejects_invalid_ids(self):
        self.assertEqual(native_call_uuid(42), 'a7100000-0000-4000-8000-00000000002a')
        for value in (0, -1, 0x1000000000000):
            with self.assertRaises(ValueError): native_call_uuid(value)

    @override_settings(MOBILE_APNS_TEAM_ID='team', MOBILE_APNS_KEY_ID='key', MOBILE_APNS_PRIVATE_KEY='test', MOBILE_IOS_BUNDLE_ID='com.awinlink.app')
    @patch('jwt.encode', return_value='signed')
    @patch('httpx.Client')
    def test_transport_environment_headers_expiry_and_invalid_token_cleanup(self, client, sign):
        VoipPushToken.objects.create(user=self.user, token=self.token, environment='development', expo_token='ExpoPushToken[test]')
        post = client.return_value.__enter__.return_value.post
        post.return_value.status_code = 200
        data = {'call_id': 42, 'uuid': native_call_uuid(42), 'expires_at': time.time() + 30}
        self.assertEqual(send_voip_call_push(self.user.pk, data), {'ExpoPushToken[test]'})
        self.assertIn('api.sandbox.push.apple.com', post.call_args.args[0])
        headers = post.call_args.kwargs['headers']
        self.assertEqual(headers['apns-topic'], 'com.awinlink.app.voip')
        self.assertEqual(headers['apns-push-type'], 'voip')
        client.assert_called_with(http2=True, timeout=5)
        VoipPushToken.objects.update(environment='production')
        post.return_value.status_code = 410
        self.assertEqual(send_voip_call_push(self.user.pk, data), set())
        self.assertIn('https://api.push.apple.com/', post.call_args.args[0])
        self.assertFalse(VoipPushToken.objects.exists())
        post.reset_mock()
        send_voip_call_push(self.user.pk, {**data, 'expires_at': 1})
        post.assert_not_called()

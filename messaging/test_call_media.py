import base64
import hashlib
import hmac
from types import SimpleNamespace
from unittest.mock import patch
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate
from .api_views import CallIceServersAPIView


class CallIceConfigurationTests(SimpleTestCase):
    def request(self, authenticated=True):
        request = APIRequestFactory().get('/api/messaging/calls/ice-servers/')
        if authenticated:
            force_authenticate(request, user=SimpleNamespace(pk=7, is_authenticated=True))
        return CallIceServersAPIView.as_view()(request)

    @override_settings(TURN_SERVER_URLS='turn:relay.test:3478, turns:relay.test:5349,https://invalid.test', TURN_SHARED_SECRET='test-secret')
    @patch('messaging.api_views.time.time', return_value=1000)
    def test_relay_credentials_expire_and_cannot_be_cached(self, _time):
        response = self.request()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertTrue(response.data['relay_configured'])
        relay = response.data['ice_servers'][1]
        self.assertEqual(relay['urls'], ['turn:relay.test:3478', 'turns:relay.test:5349'])
        self.assertEqual(relay['username'], '4600:7')
        expected = base64.b64encode(hmac.new(b'test-secret', b'4600:7', hashlib.sha1).digest()).decode()
        self.assertEqual(relay['credential'], expected)

    @override_settings(TURN_SERVER_URLS='turn:relay.test', TURN_SHARED_SECRET='')
    def test_missing_secret_reports_stun_only(self):
        response = self.request()
        self.assertFalse(response.data['relay_configured'])
        self.assertEqual(len(response.data['ice_servers']), 1)

    def test_credentials_require_authentication(self):
        self.assertEqual(self.request(False).status_code, 401)

    @override_settings(TURN_REQUIRED=True, TURN_SERVER_URLS='', TURN_SHARED_SECRET='')
    def test_required_turn_fails_closed_without_credentials(self):
        response = self.request()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data['code'], 'turn_unavailable')
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertNotIn('ice_servers', response.data)

    @override_settings(TURN_REQUIRED=True, TURN_SERVER_URLS='turn:relay.test:3478?transport=udp,turns:relay.test:443?transport=tcp', TURN_SHARED_SECRET='a' * 64, TURN_CREDENTIAL_TTL_SECONDS='1800', CALL_ICE_TRANSPORT_POLICY='relay')
    @patch('messaging.api_views.time.time', return_value=1000)
    def test_production_relay_policy_and_configurable_expiry(self, _time):
        response = self.request()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['ice_transport_policy'], 'relay')
        self.assertEqual(response.data['ice_servers'][1]['username'], '2800:7')
        self.assertNotIn('a' * 64, str(response.data))

    @override_settings(TURN_REQUIRED=True, TURN_SHARED_SECRET='a' * 64)
    def test_invalid_urls_and_parameters_fail_without_echoing_values(self):
        for url in ['turn:user:password@relay.test:3478', 'turn:relay.test:99999', 'turns:relay.test?transport=udp', 'https://relay.test', 'turn:relay.test/path']:
            with override_settings(TURN_SERVER_URLS=url):
                response = self.request()
                self.assertEqual(response.status_code, 503)
                self.assertNotIn(url, str(response.data))
        for ttl in ['no-secret-echo', 0, 86401]:
            with override_settings(TURN_SERVER_URLS='turn:relay.test', TURN_CREDENTIAL_TTL_SECONDS=ttl):
                self.assertEqual(self.request().status_code, 503)
        with override_settings(TURN_SERVER_URLS='turn:relay.test', CALL_ICE_TRANSPORT_POLICY='bad-policy'):
            self.assertEqual(self.request().status_code, 503)

    @override_settings(TURN_REQUIRED=True, TURN_SERVER_URLS='turn:relay.test', TURN_SHARED_SECRET='short')
    def test_weak_shared_secret_is_rejected_in_required_mode(self):
        self.assertEqual(self.request().status_code, 503)

    @override_settings(TURN_REQUIRED=True, TURN_SERVER_URLS='turn:relay.test', TURN_SHARED_SECRET='a' * 64)
    def test_check_command_only_reports_redacted_metadata(self):
        from io import StringIO
        from django.core.management import call_command
        output = StringIO()
        call_command('check_turn', stdout=output)
        self.assertIn('"production_ready": true', output.getvalue())
        self.assertNotIn('a' * 64, output.getvalue())
        self.assertNotIn('relay.test', output.getvalue())

    @override_settings(TURN_SERVER_URLS='turn:user:do-not-echo@relay.test', TURN_SHARED_SECRET='do-not-echo')
    def test_check_command_fails_safely(self):
        from io import StringIO
        from django.core.management import call_command
        from django.core.management.base import CommandError
        output = StringIO()
        with self.assertRaises(CommandError):
            call_command('check_turn', stdout=output)
        self.assertNotIn('do-not-echo', output.getvalue())
        self.assertNotIn('relay.test', output.getvalue())

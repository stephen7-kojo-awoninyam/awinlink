import json
import socket
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase, override_settings
from django.urls import reverse

from .models import Notification, PushSubscription
from .push import send_push_notification
from .push_security import SafePushSession, validate_push_endpoint


class PushDestinationTests(SimpleTestCase):
    def test_supported_browser_services_and_query_tokens_work(self):
        for endpoint in ['https://fcm.googleapis.com/fcm/send/device',
                         'https://updates.push.services.mozilla.com/wpush/v2/device',
                         'https://web.push.apple.com/device',
                         'https://wns2-test.notify.windows.com/w/?token=fixture']:
            self.assertEqual(validate_push_endpoint(endpoint), endpoint)

    def test_arbitrary_hosts_credentials_ports_and_lookalikes_are_rejected(self):
        for endpoint in ['https://127.0.0.1/private', 'https://[::1]/private', 'https://service.railway.internal/private',
                         'https://attacker.example/push', 'https://fcm.googleapis.com.attacker.example/push',
                         'https://notify.windows.com.attacker.example/push', 'https://user:password@fcm.googleapis.com/push',
                         'https://fcm.googleapis.com:444/push', 'http://fcm.googleapis.com/push',
                         'https://fcm.googleapis.com/push#fragment', 'https://fcm.googleapis.com/push\r\nheader']:
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                validate_push_endpoint(endpoint)

    @patch('notifications.push_security.socket.getaddrinfo')
    def test_private_or_mixed_dns_answers_never_reach_http(self, dns):
        dns.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))]
        with SafePushSession() as session, patch('requests.Session.post') as post:
            with self.assertRaises(ValueError):
                session.post('https://fcm.googleapis.com/fcm/send/device')
            post.assert_not_called()

    @patch('notifications.push_security.socket.getaddrinfo', return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 443))])
    def test_delivery_disables_redirects_proxies_and_uses_bounded_timeouts(self, dns):
        with SafePushSession() as session, patch('requests.Session.post', return_value=Mock(status_code=302)) as post:
            session.post('https://fcm.googleapis.com/fcm/send/device', allow_redirects=True, timeout=None)
            self.assertFalse(session.trust_env)
            self.assertFalse(post.call_args.kwargs['allow_redirects'])
            self.assertEqual(post.call_args.kwargs['timeout'], (3, 5))


@override_settings(AUTH_RATE_LIMIT_CACHE_ALIAS='default', AUTH_RATE_LIMIT_REQUIRE_SHARED_CACHE=False,
                   WEB_PUSH_PUBLIC_KEY='public-fixture', WEB_PUSH_PRIVATE_KEY='private-fixture')
class PushDeliveryTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.user = get_user_model().objects.create_user(username='push-destination-owner')
        self.client.force_login(self.user)
        self.notification = Notification.objects.create(user=self.user, notification_type='SYSTEM', message='Fixture')

    def test_registration_rejects_ssrf_destination(self):
        response = self.client.post(reverse('manage_push_subscription'),
            json.dumps({'endpoint': 'https://127.0.0.1/private', 'keys': {'p256dh': 'fixture', 'auth': 'fixture'}}), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(PushSubscription.objects.exists())

    @patch('pywebpush.webpush')
    def test_legacy_unsafe_subscription_is_not_delivered(self, push):
        PushSubscription.objects.create(user=self.user, endpoint='https://internal.example/private', keys={})
        send_push_notification(self.notification)
        push.assert_not_called()

    @patch('pywebpush.webpush')
    def test_supported_subscription_uses_safe_transport(self, push):
        PushSubscription.objects.create(user=self.user, endpoint='https://fcm.googleapis.com/fcm/send/device-fixture', keys={})
        send_push_notification(self.notification)
        self.assertIsInstance(push.call_args.kwargs['requests_session'], SafePushSession)
        self.assertEqual(push.call_args.kwargs['timeout'], 5)

    @patch('pywebpush.webpush', side_effect=RuntimeError('private-device-token'))
    def test_delivery_errors_do_not_log_tokens(self, push):
        PushSubscription.objects.create(user=self.user, endpoint='https://fcm.googleapis.com/fcm/send/device-fixture', keys={})
        with self.assertLogs('notifications.push', level='WARNING') as logs:
            send_push_notification(self.notification)
        self.assertNotIn('private-device-token', str(logs.output))

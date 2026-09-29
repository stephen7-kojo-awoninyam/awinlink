import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from messaging.api_views import CALL_RING_TIMEOUT, expire_ringing_call
from messaging.models import Call, CallParticipant, Conversation, ConversationParticipant
from .models import Notification, PushSubscription


class NotificationViewTests(TestCase):
	def setUp(self):
		user_model = get_user_model()
		self.user = user_model.objects.create_user(
			username="notification_owner",
			password="TestPass123!",
		)
		self.other_user = user_model.objects.create_user(
			username="notification_other",
			password="TestPass123!",
		)
		self.notification = Notification.objects.create(
			user=self.user,
			notification_type="MESSAGE",
			message="You have a new message.",
		)
		self.client.force_login(self.user)

	def test_opening_list_does_not_mark_notifications_read(self):
		response = self.client.get(reverse("notification_list"))

		self.assertEqual(response.status_code, 200)
		self.notification.refresh_from_db()
		self.assertFalse(self.notification.is_read)

	def test_single_and_bulk_read_actions_require_post(self):
		single_response = self.client.get(
			reverse("mark_notification_read", args=[self.notification.id])
		)
		self.assertEqual(single_response.status_code, 405)
		self.notification.refresh_from_db()
		self.assertFalse(self.notification.is_read)

		bulk_response = self.client.get(reverse("mark_all_notifications_read"))
		self.assertEqual(bulk_response.status_code, 405)

		response = self.client.post(
			reverse("mark_notification_read", args=[self.notification.id])
		)
		self.assertEqual(response.status_code, 302)
		self.notification.refresh_from_db()
		self.assertTrue(self.notification.is_read)

	def test_notification_detail_is_limited_to_its_owner(self):
		self.client.force_login(self.other_user)

		response = self.client.get(
			reverse("notification_detail", args=[self.notification.id])
		)

		self.assertEqual(response.status_code, 404)
		self.notification.refresh_from_db()
		self.assertFalse(self.notification.is_read)

	def test_push_subscription_requires_valid_keys_and_is_user_scoped(self):
		endpoint = "https://push.example.test/subscription/123"
		response = self.client.post(
			reverse("manage_push_subscription"),
			data=json.dumps({
				"endpoint": endpoint,
				"keys": {"p256dh": "public-key", "auth": "auth-secret"},
			}),
			content_type="application/json",
		)

		self.assertEqual(response.status_code, 201)
		subscription = PushSubscription.objects.get(endpoint=endpoint)
		self.assertEqual(subscription.user, self.user)

		invalid_response = self.client.post(
			reverse("manage_push_subscription"),
			data=json.dumps({"endpoint": endpoint, "keys": {}}),
			content_type="application/json",
		)
		self.assertEqual(invalid_response.status_code, 400)

	def test_push_subscription_cannot_be_claimed_by_another_account(self):
		endpoint = "https://push.example.test/subscription/shared"
		PushSubscription.objects.create(
			user=self.user,
			endpoint=endpoint,
			keys={"p256dh": "owner-key", "auth": "owner-auth"},
		)
		self.client.force_login(self.other_user)

		response = self.client.post(
			reverse("manage_push_subscription"),
			data=json.dumps({
				"endpoint": endpoint,
				"keys": {"p256dh": "attacker-key", "auth": "attacker-auth"},
			}),
			content_type="application/json",
		)

		self.assertEqual(response.status_code, 409)
		subscription = PushSubscription.objects.get(endpoint=endpoint)
		self.assertEqual(subscription.user, self.user)
		self.assertEqual(subscription.keys["p256dh"], "owner-key")

	@override_settings(WEB_PUSH_PUBLIC_KEY="public", WEB_PUSH_PRIVATE_KEY="private")
	def test_push_configuration_returns_public_key_only(self):
		response = self.client.get(reverse("push_config"))

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json(), {"public_key": "public", "configured": True})

	def test_notification_delivery_is_scheduled_after_commit(self):
		with patch("notifications.signals.publish_notification") as publish:
			with self.captureOnCommitCallbacks(execute=True):
				notification = Notification.objects.create(
					user=self.user,
					notification_type="SYSTEM",
					message="A new update.",
				)

		publish.assert_called_once_with(notification.id)


class NotificationAPITests(TestCase):
	def test_notification_list_only_returns_the_authenticated_users_items(self):
		user_model = get_user_model()
		user = user_model.objects.create_user(username="api_notification_user")
		other_user = user_model.objects.create_user(username="api_notification_other")
		own = Notification.objects.create(
			user=user,
			notification_type="SYSTEM",
			message="For this user",
		)
		Notification.objects.create(
			user=other_user,
			notification_type="SYSTEM",
			message="For another user",
		)
		client = APIClient()
		client.force_authenticate(user=user)

		response = client.get("/api/notifications/")

		self.assertEqual(response.status_code, 200)
		self.assertEqual([item["id"] for item in response.data], [own.id])


class MissedCallNotificationTests(TestCase):
	def create_expired_call(self, prefix):
		user_model = get_user_model()
		caller = user_model.objects.create_user(username=f"{prefix}_sender")
		recipient = user_model.objects.create_user(username=f"{prefix}_receiver")
		conversation = Conversation.objects.create(created_by=caller)
		ConversationParticipant.objects.create(conversation=conversation, user=caller)
		ConversationParticipant.objects.create(conversation=conversation, user=recipient)
		call = Call.objects.create(
			conversation=conversation,
			initiated_by=caller,
			call_type="VIDEO",
			status="RINGING",
		)
		CallParticipant.objects.create(call=call, user=caller, status="JOINED")
		CallParticipant.objects.create(call=call, user=recipient, status="RINGING")
		Call.objects.filter(pk=call.pk).update(
			started_at=timezone.now() - CALL_RING_TIMEOUT - timedelta(seconds=1)
		)
		call.refresh_from_db()
		return caller, recipient, conversation, call

	def test_expired_call_notifies_ringing_users_once(self):
		user_model = get_user_model()
		caller = user_model.objects.create_user(username="missed_call_sender")
		recipient = user_model.objects.create_user(username="missed_call_receiver")
		conversation = Conversation.objects.create(created_by=caller)
		ConversationParticipant.objects.create(conversation=conversation, user=caller)
		ConversationParticipant.objects.create(conversation=conversation, user=recipient)
		call = Call.objects.create(
			conversation=conversation,
			initiated_by=caller,
			call_type="VIDEO",
			status="RINGING",
		)
		recipient_participant = CallParticipant.objects.create(
			call=call,
			user=recipient,
			status="RINGING",
		)
		CallParticipant.objects.create(
			call=call,
			user=caller,
			status="JOINED",
		)
		Call.objects.filter(pk=call.pk).update(
			started_at=timezone.now() - CALL_RING_TIMEOUT - timedelta(seconds=1)
		)
		call.refresh_from_db()

		self.assertTrue(expire_ringing_call(call))
		self.assertFalse(expire_ringing_call(call))

		call.refresh_from_db()
		recipient_participant.refresh_from_db()
		self.assertEqual(call.status, "MISSED")
		self.assertEqual(recipient_participant.status, "MISSED")
		self.assertEqual(
			Notification.objects.filter(
				user=recipient,
				notification_type="MISSED_CALL",
				conversation=conversation,
			).count(),
			1,
		)

	def test_call_before_timeout_is_not_marked_missed(self):
		caller = get_user_model().objects.create_user(username="early_call_sender")
		recipient = get_user_model().objects.create_user(username="early_call_receiver")
		conversation = Conversation.objects.create(created_by=caller)
		call = Call.objects.create(
			conversation=conversation,
			initiated_by=caller,
			call_type="VOICE",
			status="RINGING",
		)

		self.assertFalse(expire_ringing_call(call))
		call.refresh_from_db()
		self.assertEqual(call.status, "RINGING")
		self.assertFalse(
			Notification.objects.filter(
				user=recipient,
				notification_type="MISSED_CALL",
			).exists()
		)

	def test_recipient_timeout_endpoint_creates_missed_call_notification(self):
		caller, recipient, conversation, call = self.create_expired_call("recipient_timeout")
		client = APIClient()
		client.force_authenticate(user=recipient)

		response = client.post(
			f"/api/messaging/calls/{call.id}/reject/",
			{"timed_out": True},
			format="json",
		)

		self.assertEqual(response.status_code, 200)
		call.refresh_from_db()
		self.assertEqual(call.status, "MISSED")
		self.assertTrue(
			Notification.objects.filter(
				user=recipient,
				sender=caller,
				notification_type="MISSED_CALL",
				conversation=conversation,
			).exists()
		)

	def test_caller_timeout_endpoint_creates_missed_call_notification(self):
		caller, recipient, conversation, call = self.create_expired_call("caller_timeout")
		client = APIClient()
		client.force_authenticate(user=caller)

		response = client.post(
			f"/api/messaging/calls/{call.id}/end/",
			{"end_for_everyone": True},
			format="json",
		)

		self.assertEqual(response.status_code, 200)
		call.refresh_from_db()
		self.assertEqual(call.status, "MISSED")
		self.assertTrue(
			Notification.objects.filter(
				user=recipient,
				sender=caller,
				notification_type="MISSED_CALL",
				conversation=conversation,
			).exists()
		)

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

from notifications.models import Notification
from .models import Connection


class SendConnectionRequestTests(TestCase):
	def setUp(self):
		user_model = get_user_model()
		self.sender = user_model.objects.create_user(
			username="feed_visitor",
			password="TestPass123!",
		)
		self.receiver = user_model.objects.create_user(
			username="feed_talent",
			password="TestPass123!",
		)
		self.client.force_login(self.sender)
		self.url = reverse(
			"connections:send_connection_request",
			args=[self.receiver.id],
		)

	def test_ajax_request_returns_state_without_redirecting(self):
		response = self.client.post(
			self.url,
			HTTP_X_REQUESTED_WITH="XMLHttpRequest",
			HTTP_ACCEPT="application/json",
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()["state"], "request_sent")
		self.assertEqual(Connection.objects.count(), 1)
		self.assertTrue(
			Notification.objects.filter(
				user=self.receiver,
				notification_type="INVITATION",
			).exists()
		)

	def test_duplicate_request_does_not_create_duplicate_notifications(self):
		self.client.post(
			self.url,
			HTTP_X_REQUESTED_WITH="XMLHttpRequest",
			HTTP_ACCEPT="application/json",
		)

		response = self.client.post(
			self.url,
			HTTP_X_REQUESTED_WITH="XMLHttpRequest",
			HTTP_ACCEPT="application/json",
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()["state"], "request_sent")
		self.assertEqual(Connection.objects.count(), 1)
		self.assertEqual(
			Notification.objects.filter(
				user=self.receiver,
				notification_type="INVITATION",
			).count(),
			1,
		)

	def test_rejected_outgoing_request_can_be_resent_without_replacing_row(self):
		connection = Connection.objects.create(
			sender=self.sender,
			receiver=self.receiver,
			status="REJECTED",
		)

		response = self.client.post(
			self.url,
			HTTP_X_REQUESTED_WITH="XMLHttpRequest",
			HTTP_ACCEPT="application/json",
		)

		connection.refresh_from_db()
		self.assertEqual(response.json()["state"], "request_sent")
		self.assertEqual(connection.status, "PENDING")
		self.assertEqual(Connection.objects.count(), 1)

	def test_reverse_pending_request_is_reported_instead_of_duplicated(self):
		connection = Connection.objects.create(
			sender=self.receiver,
			receiver=self.sender,
			status="PENDING",
		)

		response = self.client.post(
			self.url,
			HTTP_X_REQUESTED_WITH="XMLHttpRequest",
			HTTP_ACCEPT="application/json",
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()["state"], "incoming_request")
		self.assertEqual(response.json()["connection_id"], connection.id)
		self.assertEqual(Connection.objects.count(), 1)

	def test_connection_request_route_rejects_get(self):
		response = self.client.get(self.url)

		self.assertEqual(response.status_code, 405)

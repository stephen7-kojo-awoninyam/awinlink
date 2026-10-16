from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse

from notifications.models import Notification
from .models import Connection, Follow


@override_settings(
	STORAGES={
		"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
		"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
	}
)
class ConnectionsUITests(TestCase):
	def setUp(self):
		user_model = get_user_model()
		self.viewer = user_model.objects.create_user(username="connections_viewer")
		self.follower = user_model.objects.create_user(username="connections_follower")
		self.following_user = user_model.objects.create_user(username="connections_followed")
		self.suggestion = user_model.objects.create_user(username="connections_suggestion")
		self.client.force_login(self.viewer)

	def test_connections_page_renders_accessible_responsive_follow_tabs(self):
		Follow.objects.create(follower=self.follower, following=self.viewer)
		Follow.objects.create(follower=self.viewer, following=self.following_user)
		Connection.objects.create(sender=self.follower, receiver=self.viewer, status="PENDING")

		response = self.client.get(reverse("connections:connections_list"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'role="tablist" aria-label="Your connections"')
		for label in ("Followers", "Following", "Requests", "Suggestions"):
			self.assertContains(response, label)
		self.assertContains(response, 'role="tabpanel"')
		self.assertContains(response, 'class="person-card"')
		self.assertContains(response, f'@{self.follower.username}')
		self.assertContains(response, f'@{self.following_user.username}')
		self.assertContains(response, f'@{self.suggestion.username}')
		self.assertContains(response, 'aria-label="Unfollow connections_followed"')
		self.assertContains(response, 'aria-label="Decline request from connections_follower"')
		self.assertContains(response, 'static/css/connections.css')
		self.assertContains(response, 'static/js/connections.js')

	def test_connections_page_requires_login(self):
		self.client.logout()
		response = self.client.get(reverse("connections:connections_list"))
		self.assertEqual(response.status_code, 302)


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

	def test_accept_request_returns_json_without_redirecting(self):
		connection = Connection.objects.create(
			sender=self.receiver,
			receiver=self.sender,
			status="PENDING",
		)

		response = self.client.post(
			reverse("connections:accept_connection_request", args=[connection.id]),
			HTTP_X_REQUESTED_WITH="XMLHttpRequest",
			HTTP_ACCEPT="application/json",
		)

		connection.refresh_from_db()
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()["state"], "connected")
		self.assertEqual(connection.status, "ACCEPTED")

	def test_reject_request_returns_json_without_redirecting(self):
		connection = Connection.objects.create(
			sender=self.receiver,
			receiver=self.sender,
			status="PENDING",
		)

		response = self.client.post(
			reverse("connections:reject_connection_request", args=[connection.id]),
			HTTP_X_REQUESTED_WITH="XMLHttpRequest",
			HTTP_ACCEPT="application/json",
		)

		connection.refresh_from_db()
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()["state"], "rejected")
		self.assertEqual(connection.status, "REJECTED")

	def test_cancel_request_returns_json_without_redirecting(self):
		connection = Connection.objects.create(
			sender=self.sender,
			receiver=self.receiver,
			status="PENDING",
		)

		response = self.client.post(
			reverse("connections:cancel_connection_request", args=[connection.id]),
			HTTP_X_REQUESTED_WITH="XMLHttpRequest",
			HTTP_ACCEPT="application/json",
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()["state"], "cancelled")
		self.assertFalse(Connection.objects.filter(id=connection.id).exists())

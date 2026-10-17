from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse, resolve
from rest_framework.test import APIClient
from notifications.models import Notification
from .models import Connection


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class ConnectionResponseTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.sender = users.objects.create_user(username="sender")
        self.receiver = users.objects.create_user(username="receiver")
        self.other = users.objects.create_user(username="other")
        self.connection = Connection.objects.create(sender=self.sender, receiver=self.receiver)
        self.client.force_login(self.receiver)
        self.api = APIClient()
        self.api.force_authenticate(self.receiver)

    def web_url(self, action):
        return reverse(f"connections:{action}_connection_request", args=[self.connection.pk])

    def test_web_and_capitalized_routes_accept_and_reject_idempotently(self):
        for action, expected in (("accept", "ACCEPTED"), ("reject", "REJECTED")):
            self.connection.status = "PENDING"
            self.connection.save()
            for url in (self.web_url(action), f"/Connections/connection/{self.connection.pk}/{action}/"):
                self.assertIsNotNone(resolve(url))
                response = self.client.post(url, HTTP_ACCEPT="application/json")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["connection_id"], self.connection.pk)
            self.connection.refresh_from_db()
            self.assertEqual(self.connection.status, expected)
        self.assertEqual(Notification.objects.filter(notification_type="CONNECTION").count(), 1)

    def test_web_redirect_and_safe_fallback(self):
        response = self.client.post(self.web_url("accept"))
        self.assertRedirects(response, reverse("connections:connections_list"), fetch_redirect_response=False)
        response = self.client.post(self.web_url("accept"), HTTP_REFERER="https://evil.example/")
        self.assertRedirects(response, reverse("connections:connections_list"), fetch_redirect_response=False)

    def test_receiver_ownership_methods_missing_and_conflicts(self):
        for action in ("accept", "reject"):
            self.assertEqual(self.client.get(self.web_url(action)).status_code, 405)
            for user in (self.sender, self.other):
                self.client.force_login(user)
                self.assertEqual(self.client.post(self.web_url(action)).status_code, 403)
            self.client.force_login(self.receiver)
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.status, "PENDING")
        self.assertEqual(self.client.post("/connections/connection/999999/accept/").status_code, 404)
        self.client.post(self.web_url("accept"))
        self.assertEqual(self.client.post(self.web_url("reject")).status_code, 409)
        self.client.logout()
        self.assertEqual(self.client.post(self.web_url("reject")).status_code, 302)

    def test_mobile_patch_and_post_endpoints_share_response_behavior(self):
        for action, expected in (("accept", "ACCEPTED"), ("reject", "REJECTED")):
            self.connection.status = "PENDING"
            self.connection.save()
            url = f"/api/connections/{self.connection.pk}/respond/"
            response = self.api.patch(url, {"status": expected}, format="json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], expected)
            self.assertEqual(self.api.post(f"/api/connections/{self.connection.pk}/{action}/").status_code, 200)
            opposite = "REJECTED" if expected == "ACCEPTED" else "ACCEPTED"
            self.assertEqual(self.api.patch(url, {"status": opposite}, format="json").status_code, 409)
        self.assertEqual(Notification.objects.filter(notification_type="CONNECTION").count(), 1)

    def test_mobile_ownership_and_validation(self):
        url = f"/api/connections/{self.connection.pk}/respond/"
        self.assertEqual(self.api.patch(url, {"status": "PENDING"}, format="json").status_code, 400)
        for user in (self.sender, self.other):
            self.api.force_authenticate(user)
            self.assertEqual(self.api.patch(url, {"status": "ACCEPTED"}, format="json").status_code, 403)
            for action in ("accept", "reject"):
                self.assertEqual(self.api.post(f"/api/connections/{self.connection.pk}/{action}/").status_code, 403)

    def test_template_posts_connection_id_only_for_incoming_requests(self):
        outgoing = Connection.objects.create(sender=self.receiver, receiver=self.other)
        response = self.client.get(reverse("connections:connections_list"))
        for action in ("accept", "reject"):
            self.assertContains(response, f'action="{self.web_url(action)}"')
            self.assertNotContains(response, f'action="/connections/connection/{outgoing.pk}/{action}/"')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')

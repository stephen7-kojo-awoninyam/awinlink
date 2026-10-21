"""Real browser and native-screen logic against an isolated PostgreSQL HTTP server."""
import json
import os
from pathlib import Path
import subprocess
from unittest import skipUnless

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.db import connection
from django.test import Client, override_settings
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import User
from talents.models import TalentProfile
from .models import Organization, OrganizationMembership, OrganizationTalent, OrganizationTalentEvent


@skipUnless(connection.vendor == "postgresql", "Roster HTTP E2E uses an isolated PostgreSQL test database")
@override_settings(ALLOWED_HOSTS=["localhost", "127.0.0.1", "testserver"], SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    STORAGES={"default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
              "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class RosterEndToEndTests(StaticLiveServerTestCase):
    def setUp(self):
        self.users = {key: User.objects.create_user(username=f"roster_e2e_{key}", role="ORGANIZATION" if key == "owner" else "ATHLETE")
                      for key in ["owner", "manager", "talent", "outsider"]}
        self.org = Organization.objects.create(user=self.users["owner"], name="Roster E2E Academy", country="GH")
        self.talent = TalentProfile.objects.create(user=self.users["talent"], profile_visibility="PUBLIC")
        self.members = {}
        for key, role in [("owner", "OWNER"), ("manager", "MANAGER"), ("talent", "VIEWER")]:
            self.members[key] = OrganizationMembership.objects.create(organization=self.org, user=self.users[key], role=role)
        self.sessions = {}
        for key, user in self.users.items():
            client = Client(); client.force_login(user)
            self.sessions[key] = client.cookies[settings.SESSION_COOKIE_NAME].value

    def run_client(self, script):
        root = Path(__file__).resolve().parents[1]
        fixture = {"origin": self.live_server_url, "organization": self.org.pk, "talent_id": self.talent.pk,
            "talent_username": self.users["talent"].username, "talent_membership": self.members["talent"].pk,
            "sessions": self.sessions, "cookie_name": settings.SESSION_COOKIE_NAME,
            "tokens": {key: str(AccessToken.for_user(user)) for key, user in self.users.items()}}
        result = subprocess.run(["node", str(root / "scripts" / script)], input=json.dumps(fixture),
            capture_output=True, text=True, timeout=240, cwd=root,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["passed"])
        self.assertEqual(User.objects.count(), 4, "Unclaimed entries must not create login accounts")
        self.assertTrue(OrganizationTalent.objects.filter(status="REMOVED").exists())
        self.assertTrue(OrganizationTalent.objects.filter(status="DECLINED").exists())
        self.assertTrue(OrganizationTalentEvent.objects.filter(action="CONFIRM").exists())
        self.assertTrue(OrganizationTalentEvent.objects.filter(action="REMOVE").exists())

    def test_mobile_screen_lifecycle_over_real_jwt_http(self):
        self.run_client("roster_mobile_e2e.cjs")

    @skipUnless(os.environ.get("ROSTER_TEST_CHROME"), "Set ROSTER_TEST_CHROME to exercise real browser controls")
    def test_web_browser_controls_with_session_csrf_and_mobile_viewport(self):
        OrganizationTalent.objects.bulk_create([OrganizationTalent(organization=self.org, name=f"Pagination player {i:02}", tag="Member") for i in range(51)])
        self.run_client("roster_browser_e2e.cjs")

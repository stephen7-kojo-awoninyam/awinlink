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
from .models import Organization, OrganizationTalent, TalentAgreement


@skipUnless(connection.vendor == "postgresql", "Agreement HTTP tests use isolated PostgreSQL")
@override_settings(ALLOWED_HOSTS=["localhost", "127.0.0.1", "testserver"], SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    STORAGES={"default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
              "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class AgreementEndToEndTests(StaticLiveServerTestCase):
    def setUp(self):
        self.users = {key: User.objects.create_user(username=f"agreement_http_{key}") for key in ["origin", "destination", "talent", "outsider"]}
        self.origin = Organization.objects.create(user=self.users["origin"], name="Agreement Origin", country="GH")
        self.destination = Organization.objects.create(user=self.users["destination"], name="Agreement Destination", country="GH")
        self.talent = TalentProfile.objects.create(user=self.users["talent"], profile_visibility="PUBLIC")
        self.entry = OrganizationTalent.objects.create(organization=self.origin, talent=self.talent, name="HTTP talent", tag="Player", roster="Academy", status="CONFIRMED")

    def run_client(self, name):
        sessions = {}
        for key, user in self.users.items():
            client = Client(); client.force_login(user); sessions[key] = client.cookies[settings.SESSION_COOKIE_NAME].value
        fixture = {"origin": self.live_server_url, "entry": self.entry.pk, "organization": self.origin.pk,
            "destination": self.destination.pk, "sessions": sessions, "cookie_name": settings.SESSION_COOKIE_NAME,
            "tokens": {key: str(AccessToken.for_user(user)) for key, user in self.users.items()}}
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(["node", str(root / "scripts" / name)], input=json.dumps(fixture), capture_output=True,
            text=True, cwd=root, timeout=240, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["passed"])
        self.entry.refresh_from_db(); self.assertEqual(self.entry.status, "REMOVED")
        self.assertEqual(OrganizationTalent.objects.filter(organization=self.destination, status="CONFIRMED").count(), 1)
        self.assertTrue(TalentAgreement.objects.filter(status="ENDED").exists())
        self.assertTrue(TalentAgreement.objects.filter(kind="TRANSFER", status="COMPLETED").exists())
        self.assertEqual(User.objects.count(), 4)

    def test_mobile_agreement_client_over_real_jwt_http(self):
        self.run_client("agreement_mobile_e2e.cjs")

    @skipUnless(os.environ.get("AGREEMENT_TEST_CHROME"), "Set AGREEMENT_TEST_CHROME for real browser controls")
    def test_web_consent_revision_transfer_and_ending_controls(self):
        self.run_client("agreement_browser_e2e.cjs")

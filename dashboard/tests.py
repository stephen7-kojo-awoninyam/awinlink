import re

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from organizations.models import Organization
from talents.models import TalentProfile, VerificationRequest


@override_settings(
    STORAGES={
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
)
class AdminMutationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(username="platform_admin", role="ADMIN")
        cls.superuser = User.objects.create_superuser(
            username="platform_superuser", email="admin@example.com",
            password="TestPass123!", role="ATHLETE",
        )
        cls.talent_user = User.objects.create_user(username="talent", role="ATHLETE")
        cls.talent = TalentProfile.objects.create(user=cls.talent_user)
        cls.verification = VerificationRequest.objects.create(
            talent=cls.talent, message="Please verify my profile.",
        )
        cls.organization_user = User.objects.create_user(
            username="organization", role="ORGANIZATION",
        )
        cls.organization = Organization.objects.create(
            user=cls.organization_user, name="Example Organization", country="GH",
        )
        cls.outsiders = [
            User.objects.create_user(username=f"outsider_{role}", role=role)
            for role in ("ATHLETE", "ORGANIZATION", "SCOUT", "COACH")
        ]
        cls.outsiders.append(User.objects.create_user(
            username="staff_only", role="ATHLETE", is_staff=True,
        ))

    def actions(self):
        return (
            ("approve_verification", self.verification.pk, "verification_requests"),
            ("reject_verification", self.verification.pk, "verification_requests"),
            ("toggle_organization_status", self.organization.pk, "organization_management"),
        )

    def assert_unchanged(self):
        self.verification.refresh_from_db()
        self.talent.refresh_from_db()
        self.organization_user.refresh_from_db()
        self.organization.refresh_from_db()
        self.assertEqual(self.verification.status, "PENDING")
        self.assertIsNone(self.verification.reviewed_at)
        self.assertFalse(self.talent.verified)
        self.assertTrue(self.organization_user.is_active)
        self.assertEqual(self.organization.status, "ACTIVE")

    def csrf_client(self, actor, page):
        client = Client(enforce_csrf_checks=True)
        client.force_login(actor)
        response = client.get(reverse(page))
        self.assertEqual(response.status_code, 200)
        return client, client.cookies["csrftoken"].value

    def test_mutations_reject_non_post_methods_without_changes(self):
        self.client.force_login(self.admin)
        for name, pk, _ in self.actions():
            for method in ("GET", "HEAD", "PUT", "PATCH", "DELETE", "OPTIONS"):
                with self.subTest(action=name, method=method):
                    response = self.client.generic(method, reverse(name, args=[pk]))
                    self.assertEqual(response.status_code, 405)
                    self.assertEqual(response.headers["Allow"], "POST")
                    self.assert_unchanged()

    def test_anonymous_posts_require_login_without_changes(self):
        for name, pk, _ in self.actions():
            with self.subTest(action=name):
                url = reverse(name, args=[pk])
                response = self.client.post(url)
                self.assertRedirects(
                    response, f"{reverse('login')}?next={url}",
                    fetch_redirect_response=False,
                )
                self.assert_unchanged()

    def test_non_admin_posts_preserve_permission_denial(self):
        for actor in self.outsiders:
            self.client.force_login(actor)
            for name, pk, _ in self.actions():
                with self.subTest(actor=actor.username, action=name):
                    response = self.client.post(reverse(name, args=[pk]))
                    self.assertRedirects(
                        response, reverse("home"), fetch_redirect_response=False,
                    )
                    self.assert_unchanged()

    def test_posts_without_csrf_tokens_are_rejected_without_changes(self):
        for name, pk, page in self.actions():
            with self.subTest(action=name):
                client, _ = self.csrf_client(self.admin, page)
                response = client.post(reverse(name, args=[pk]))
                self.assertEqual(response.status_code, 403)
                self.assert_unchanged()

    def test_posts_with_invalid_csrf_tokens_are_rejected_without_changes(self):
        for name, pk, page in self.actions():
            with self.subTest(action=name):
                client, _ = self.csrf_client(self.admin, page)
                response = client.post(
                    reverse(name, args=[pk]), {"csrfmiddlewaretoken": "invalid"},
                )
                self.assertEqual(response.status_code, 403)
                self.assert_unchanged()

    def test_admin_and_superuser_csrf_posts_preserve_mutations_and_redirects(self):
        for actor in (self.admin, self.superuser):
            for name, pk, page in self.actions():
                with self.subTest(actor=actor.username, action=name):
                    self.verification.status = "PENDING"
                    self.verification.save()
                    self.talent.verified = False
                    self.talent.save()
                    self.organization_user.is_active = True
                    self.organization_user.save()
                    self.organization.status = "ACTIVE"
                    self.organization.save(update_fields=["status"])
                    client, token = self.csrf_client(actor, page)
                    response = client.post(
                        reverse(name, args=[pk]), {"csrfmiddlewaretoken": token, "status": "INACTIVE"},
                    )
                    self.assertRedirects(
                        response, reverse(page), fetch_redirect_response=False,
                    )
                    self.verification.refresh_from_db()
                    self.talent.refresh_from_db()
                    self.organization_user.refresh_from_db()
                    self.organization.refresh_from_db()
                    expected_status = {
                        "approve_verification": "APPROVED",
                        "reject_verification": "REJECTED",
                        "toggle_organization_status": "PENDING",
                    }[name]
                    self.assertEqual(self.verification.status, expected_status)
                    self.assertEqual(self.talent.verified, name == "approve_verification")
                    self.assertIsNone(self.verification.reviewed_at)
                    self.assertTrue(self.organization_user.is_active)
                    self.assertEqual(
                        self.organization.status,
                        "INACTIVE" if name == "toggle_organization_status" else "ACTIVE",
                    )
                    self.talent_user.refresh_from_db()
                    self.assertTrue(self.talent_user.is_active)

    def test_organization_can_be_reactivated_with_csrf_post(self):
        self.organization.status = "INACTIVE"
        self.organization.save(update_fields=["status"])
        client, token = self.csrf_client(self.admin, "organization_management")

        response = client.post(
            reverse("toggle_organization_status", args=[self.organization.pk]),
            {"csrfmiddlewaretoken": token, "status": "ACTIVE"},
        )

        self.assertRedirects(
            response, reverse("organization_management"), fetch_redirect_response=False,
        )
        self.assert_unchanged()

    def test_rejection_preserves_existing_talent_verification(self):
        self.talent.verified = True
        self.talent.save()
        client, token = self.csrf_client(self.admin, "verification_requests")

        response = client.post(
            reverse("reject_verification", args=[self.verification.pk]),
            {"csrfmiddlewaretoken": token, "status": "INACTIVE"},
        )

        self.assertRedirects(
            response, reverse("verification_requests"), fetch_redirect_response=False,
        )
        self.verification.refresh_from_db()
        self.talent.refresh_from_db()
        self.assertEqual(self.verification.status, "REJECTED")
        self.assertTrue(self.talent.verified)

    def test_management_actions_render_as_csrf_protected_post_forms(self):
        self.client.force_login(self.admin)
        for name, pk, page in self.actions():
            with self.subTest(action=name):
                response = self.client.get(reverse(page))
                self.assertEqual(response.status_code, 200)
                url = reverse(name, args=[pk])
                html = response.content.decode()
                form = re.search(
                    r'<form method="post" action="' + re.escape(url)
                    + r'"[^>]*>(.*?)</form>', html, re.S,
                )
                self.assertIsNotNone(form)
                self.assertIn('name="csrfmiddlewaretoken"', form.group(1))
                self.assertIn('type="submit"', form.group(1))
                self.assertNotIn(f'href="{url}"', html)

    def test_organization_status_requests_are_explicit_and_idempotent(self):
        self.client.force_login(self.admin)
        url = reverse("toggle_organization_status", args=[self.organization.pk])
        for desired_status in ("INACTIVE", "INACTIVE", "ACTIVE", "ACTIVE"):
            response = self.client.post(url, {"status": desired_status})
            self.assertRedirects(
                response, reverse("organization_management"), fetch_redirect_response=False,
            )
            self.organization.refresh_from_db()
            self.organization_user.refresh_from_db()
            self.assertEqual(self.organization.status, desired_status)
            self.assertTrue(self.organization_user.is_active)

    def test_organization_status_does_not_reenable_a_disabled_account(self):
        self.organization_user.is_active = False
        self.organization_user.save(update_fields=["is_active"])
        self.client.force_login(self.admin)
        url = reverse("toggle_organization_status", args=[self.organization.pk])
        for desired_status in ("INACTIVE", "ACTIVE"):
            self.client.post(url, {"status": desired_status})
            self.organization_user.refresh_from_db()
            self.assertFalse(self.organization_user.is_active)

    def test_ownerless_organization_can_be_suspended_and_reactivated(self):
        organization = Organization.objects.create(name="Unclaimed", country="GH")
        self.client.force_login(self.admin)
        url = reverse("toggle_organization_status", args=[organization.pk])
        for desired_status in ("INACTIVE", "ACTIVE"):
            response = self.client.post(url, {"status": desired_status})
            self.assertEqual(response.status_code, 302)
            organization.refresh_from_db()
            self.assertEqual(organization.status, desired_status)
            self.assertIsNone(organization.user_id)

    def test_invalid_status_requests_do_not_change_organization_or_account(self):
        self.client.force_login(self.admin)
        url = reverse("toggle_organization_status", args=[self.organization.pk])
        for data in ({}, {"status": "CLOSED"}, {"status": "MERGED"}, {"status": "invalid"}):
            with self.subTest(data=data):
                self.assertEqual(self.client.post(url, data).status_code, 400)
                self.assert_unchanged()

    def test_suspend_controls_do_not_reopen_closed_or_merged_records(self):
        self.client.force_login(self.admin)
        url = reverse("toggle_organization_status", args=[self.organization.pk])
        for original in ("CLOSED", "MERGED"):
            self.organization.status = original
            self.organization.save(update_fields=["status"])
            response = self.client.get(reverse("organization_management"))
            self.assertNotContains(response, f'action="{url}"')
            for desired in ("ACTIVE", "INACTIVE"):
                self.assertEqual(self.client.post(url, {"status": desired}).status_code, 400)
                self.organization.refresh_from_db()
                self.assertEqual(self.organization.status, original)

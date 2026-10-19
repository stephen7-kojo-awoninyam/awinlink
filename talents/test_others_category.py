from importlib import import_module
from types import SimpleNamespace
from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from api.serializers import TalentProfileSerializer
from talents.forms import TalentCategoryForm, TalentProfileForm
from talents.models import TalentProfile
from others.models import OtherTalentProfile


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class OthersCategoryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="specific", role="ATHLETE")
        self.profile = TalentProfile.objects.create(user=self.user, talent_category="OTHERS")

    def test_forms_require_specific_talent(self):
        for form_class in (TalentCategoryForm, TalentProfileForm):
            for area in ("", "  ", "Others", "other talent"):
                form = form_class(data={"talent_category": "OTHERS", "talent_area": area}, instance=self.profile)
                self.assertFalse(form.is_valid())
                self.assertIn("talent_area", form.errors)

    def test_categories_preserved(self):
        self.assertEqual([key for key, _ in TalentProfile.TALENT_CATEGORY_CHOICES], ["SPORTS", "SCIENCE_TECHNOLOGY", "ARTS", "OTHERS"])
        for category in ("SPORTS", "SCIENCE_TECHNOLOGY", "ARTS"):
            form = TalentCategoryForm(data={"talent_category": category})
            self.assertTrue(form.is_valid(), form.errors)

    def test_existing_user_can_repair_and_edit_via_api(self):
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.patch("/api/talents/me/", {"headline": "Hello"}, format="json")
        self.assertEqual(response.status_code, 400)
        for area in ("Public Speaking", "Culinary Arts"):
            response = client.patch("/api/talents/me/", {"talent_area": f" {area} "}, format="json")
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data["talent_area"], area)
            self.profile.refresh_from_db()
            self.assertEqual(self.profile.talent_area, area)
        self.assertEqual(client.patch("/api/talents/me/", {"talent_area": " "}, format="json").status_code, 400)
        self.assertEqual(client.get("/api/talents/me/").data["talent_area"], "Culinary Arts")

    def test_model_and_serializer_validation(self):
        with self.assertRaises(ValidationError):
            self.profile.clean()
        serializer = TalentProfileSerializer(self.profile, data={"talent_area": "x" * 151}, partial=True)
        self.assertFalse(serializer.is_valid())

    def test_discovery_and_market_use_specific_talent(self):
        from django.urls import reverse
        from django.utils import timezone
        from domains.models import TalentDomain
        from marketplace.models import Listing
        from recommendations.ecosystems import _talent_profile_topics
        self.profile.talent_area = "Public Speaking"
        self.profile.save()
        self.assertIn("public speaking", _talent_profile_topics(self.profile))
        self.client.force_login(self.user)
        response = self.client.get(reverse("user_search"), {"search": "Public Speaking"})
        self.assertContains(response, "Public Speaking")
        response = self.client.get(reverse("talent_search"), {"q": "Public Speaking"})
        self.assertContains(response, "Public Speaking")
        domain = TalentDomain.objects.create(name="Communication")
        listing = Listing.objects.create(talent=self.profile, ecosystem="OTHERS", subecosystem=domain,
            title="Available", description="Ready", status="PUBLISHED", publication_consented_at=timezone.now())
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.get("/api/marketplace/listings/", {"q": "Public Speaking"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["id"], listing.pk)
        self.assertEqual(response.data["results"][0]["talent_area"], "Public Speaking")

    def test_backfill_preserves_existing_values_and_unknowns(self):
        other = OtherTalentProfile.objects.create(talent=self.profile, specialization="Public Speaking")
        migration = import_module("talents.migrations.0015_backfill_others_talent_area")
        migration.backfill(apps, SimpleNamespace(connection=connection))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.talent_area, "Public Speaking")
        self.profile.talent_area = "Consulting"
        self.profile.save()
        migration.backfill(apps, SimpleNamespace(connection=connection))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.talent_area, "Consulting")

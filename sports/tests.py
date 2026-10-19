from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from core.management.commands.seed_domains import Command as DomainSeed
from sports.category_seeds import SPORT_CATEGORIES
from sports.models import Sport, SportCategory


class SeedSportCategoriesTests(TestCase):
    def run_seed(self, **options):
        output = StringIO()
        call_command("seed_sport_categories", stdout=output, **options)
        return output.getvalue()

    def test_all_catalog_sports_have_expected_categories_and_rerun_is_idempotent(self):
        self.assertEqual(set(SPORT_CATEGORIES), set(DomainSeed.DOMAINS["Sports"]))
        for name in SPORT_CATEGORIES:
            Sport.objects.create(name=name)
        self.run_seed()
        for sport in Sport.objects.all():
            expected = SPORT_CATEGORIES[sport.name]
            self.assertEqual(len(expected), len(set(expected)))
            self.assertSetEqual(set(sport.categories.values_list("name", flat=True)), set(expected))
            self.assertFalse(sport.categories.filter(description="").exists())
        before = list(SportCategory.objects.order_by("pk").values())
        self.assertIn("Added 0 categories", self.run_seed())
        self.assertEqual(before, list(SportCategory.objects.order_by("pk").values()))

    def test_preserves_existing_rows_including_duplicates_and_custom_categories(self):
        sport = Sport.objects.create(name="  fOoTbAlL  ", description="Keep sport")
        for name in (" goalkeeper ", "GOALKEEPER", "Academy Talent"):
            SportCategory.objects.create(sport=sport, name=name, description="Keep category")
        before = list(SportCategory.objects.values())
        self.run_seed()
        self.assertEqual(sport.categories.count(), 6)
        for row in before:
            self.assertEqual(SportCategory.objects.values().get(pk=row["id"]), row)
        sport.refresh_from_db()
        self.assertEqual(sport.description, "Keep sport")

    def test_dry_run_has_no_writes_and_reports_same_missing_count(self):
        sport = Sport.objects.create(name="Basketball")
        SportCategory.objects.create(sport=sport, name="  point   guard ")
        before = list(SportCategory.objects.values())
        with patch.object(SportCategory.objects, "bulk_create", side_effect=AssertionError("dry run wrote")):
            output = self.run_seed(dry_run=True)
        self.assertIn("Dry run: would add 4 categories", output)
        self.assertEqual(before, list(SportCategory.objects.values()))
        self.assertIn("Added 4 categories", self.run_seed())

    def test_aliases_and_categories_are_scoped_to_each_sport(self):
        soccer = Sport.objects.create(name="Soccer")
        football = Sport.objects.create(name="Football")
        self.run_seed()
        for sport in (soccer, football):
            self.assertSetEqual(set(sport.categories.values_list("name", flat=True)), set(SPORT_CATEGORIES["Football"]))

    def test_unknown_sports_reported_and_no_sports_created(self):
        sport = Sport.objects.create(name="Custom Sport")
        category = SportCategory.objects.create(sport=sport, name="Custom Category")
        self.assertIn("Skipped unsupported sport: Custom Sport", self.run_seed())
        self.assertEqual(list(Sport.objects.values_list("pk", flat=True)), [sport.pk])
        self.assertEqual(list(SportCategory.objects.values_list("pk", flat=True)), [category.pk])

    def test_empty_database_is_noop(self):
        self.assertIn("Added 0 categories", self.run_seed())
        self.assertFalse(Sport.objects.exists())

    def test_failure_rolls_back_entire_seed(self):
        Sport.objects.create(name="Football")
        Sport.objects.create(name="Basketball")
        original = SportCategory.objects.bulk_create
        calls = 0

        def fail_second_batch(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("Simulated failure")
            return original(*args, **kwargs)

        with patch.object(SportCategory.objects, "bulk_create", side_effect=fail_second_batch):
            with self.assertRaisesMessage(RuntimeError, "Simulated failure"):
                self.run_seed()
        self.assertFalse(SportCategory.objects.exists())

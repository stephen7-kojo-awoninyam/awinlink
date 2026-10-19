from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from core.management.commands.seed_domains import Command as DomainSeed
from sports.category_seeds import SPORT_CATEGORIES, normalized_name
from sports.models import Sport, SportCategory


class SeedSportCategoriesTests(TestCase):
    # Independent coverage contract: these 25 extend the original 20 sports.
    EXTENDED_SPORTS = {
        "Archery": "Field Archery",
        "Wrestling": "Greco-Roman",
        "Softball": "Designated Player",
        "Gymnastics": "Rhythmic Gymnastics",
        "Judo": "Kata",
        "Karate": "Individual Kumite",
        "Taekwondo": "Recognized Poomsae",
        "Fencing": "Sabre",
        "Weightlifting": "Clean and Jerk",
        "Shooting": "Skeet",
        "Rowing": "Single Sculls",
        "Canoeing": "Canoe Slalom",
        "Kayaking": "Kayak Cross",
        "Sailing": "Keelboat Sailing",
        "Surfing": "Shortboard",
        "Diving": "3m Springboard",
        "Water Polo": "Center Forward",
        "Skiing": "Nordic Combined",
        "Snowboarding": "Snowboard Cross",
        "Figure Skating": "Ice Dance",
        "Speed Skating": "Short Track",
        "Ice Hockey": "Goaltender",
        "Bobsleigh": "Monobob",
        "Biathlon": "Pursuit",
        "Equestrian": "Eventing",
    }

    def run_seed(self, **options):
        output = StringIO()
        call_command("seed_sport_categories", stdout=output, **options)
        return output.getvalue()

    def test_all_catalog_sports_have_expected_categories_and_rerun_is_idempotent(self):
        self.assertTrue(set(DomainSeed.DOMAINS["Sports"]).issubset(SPORT_CATEGORIES))
        for name in SPORT_CATEGORIES:
            Sport.objects.create(name=name)
        self.run_seed()
        for sport in Sport.objects.all():
            expected = SPORT_CATEGORIES[sport.name]
            self.assertEqual(len(expected), len({normalized_name(name) for name in expected}))
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

    def test_extended_sports_preserve_existing_categories_and_dry_run_counts(self):
        added = set(SPORT_CATEGORIES) - set(DomainSeed.DOMAINS["Sports"])
        self.assertSetEqual(set(self.EXTENDED_SPORTS), added)
        for name in sorted(added):
            sport = Sport.objects.create(name=f"  {name.upper()}  ")
            category = SPORT_CATEGORIES[name][0]
            SportCategory.objects.create(
                sport=sport, name="  " + "   ".join(category.upper().split()) + "  ",
                description="Keep existing specialization",
            )
            SportCategory.objects.create(sport=sport, name="Custom specialization", description="Keep custom")
        before = list(SportCategory.objects.order_by("pk").values())
        missing = sum(len(SPORT_CATEGORIES[name]) - 1 for name in added)
        with patch.object(SportCategory.objects, "bulk_create", side_effect=AssertionError("dry run wrote")):
            output = self.run_seed(dry_run=True)
        self.assertIn(f"Dry run: would add {missing} categories; 0 unsupported sports skipped.", output)
        self.assertEqual(before, list(SportCategory.objects.order_by("pk").values()))
        self.assertIn(f"Added {missing} categories; 0 unsupported sports skipped.", self.run_seed())
        for row in before:
            self.assertEqual(SportCategory.objects.values().get(pk=row["id"]), row)
        after = list(SportCategory.objects.order_by("pk").values())
        self.assertIn("Added 0 categories", self.run_seed())
        self.assertEqual(after, list(SportCategory.objects.order_by("pk").values()))

    def test_all_25_extended_sports_have_sport_specific_categories(self):
        self.assertEqual(len(self.EXTENDED_SPORTS), 25)
        for name in self.EXTENDED_SPORTS:
            Sport.objects.create(name=name)
        output = self.run_seed()
        self.assertIn("0 unsupported sports skipped", output)
        for sport in Sport.objects.all():
            with self.subTest(sport=sport.name):
                self.assertTrue(sport.categories.filter(name=self.EXTENDED_SPORTS[sport.name]).exists())
                self.assertEqual(sport.categories.count(), len(SPORT_CATEGORIES[sport.name]))
                for category in sport.categories.all():
                    self.assertTrue(category.name.strip())
                    self.assertLessEqual(len(category.name), SportCategory._meta.get_field("name").max_length)

    def test_failure_on_last_extended_sport_rolls_back_all_25_sports(self):
        sports = [Sport.objects.create(name=name) for name in self.EXTENDED_SPORTS]
        SportCategory.objects.create(sport=sports[0], name="Custom", description="Preserve")
        before = list(SportCategory.objects.values())
        original = SportCategory.objects.bulk_create
        calls = 0

        def fail_last_batch(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 25:
                raise RuntimeError("Last sport failed")
            return original(*args, **kwargs)

        with patch.object(SportCategory.objects, "bulk_create", side_effect=fail_last_batch):
            with self.assertRaisesMessage(RuntimeError, "Last sport failed"):
                self.run_seed()
        self.assertEqual(calls, 25)
        self.assertEqual(before, list(SportCategory.objects.values()))
        self.assertEqual(Sport.objects.count(), 25)

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
        Sport.objects.create(name="Archery")
        sport = Sport.objects.create(name="Wrestling")
        existing = SportCategory.objects.create(sport=sport, name="Custom", description="Keep")
        before = list(SportCategory.objects.values())
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
        self.assertEqual(before, list(SportCategory.objects.values()))
        self.assertTrue(SportCategory.objects.filter(pk=existing.pk).exists())

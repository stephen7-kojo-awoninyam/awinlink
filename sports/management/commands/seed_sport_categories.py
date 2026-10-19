from django.core.management.base import BaseCommand
from django.db import transaction

from sports.category_seeds import SPORT_ALIASES, SPORT_CATEGORIES, normalized_name
from sports.models import Sport, SportCategory


class Command(BaseCommand):
    help = "Add curated categories to existing sports without changing existing data."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Preview missing categories without writing data.")

    def handle(self, *args, **options):
        catalog = {normalized_name(name): categories for name, categories in SPORT_CATEGORIES.items()}
        for alias, name in SPORT_ALIASES.items():
            catalog[alias] = SPORT_CATEGORIES[name]

        dry_run = options["dry_run"]
        total = skipped = 0
        # Lock parents in a stable order to serialize concurrent command runs on
        # databases supporting row locks. No schema or existing-row changes.
        with transaction.atomic():
            sports = Sport.objects.order_by("pk")
            if not dry_run:
                sports = sports.select_for_update()
            for sport in sports:
                categories = catalog.get(normalized_name(sport.name))
                if categories is None:
                    skipped += 1
                    self.stdout.write(self.style.WARNING(f"Skipped unsupported sport: {sport.name}"))
                    continue
                existing = {
                    normalized_name(name)
                    for name in sport.categories.values_list("name", flat=True)
                }
                missing = []
                for name in categories:
                    key = normalized_name(name)
                    if key not in existing:
                        missing.append(SportCategory(
                            sport=sport, name=name,
                            description=f"{sport.name}: {name} position, discipline or specialization.",
                        ))
                        existing.add(key)
                if not dry_run:
                    SportCategory.objects.bulk_create(missing, batch_size=500)
                total += len(missing)
                self.stdout.write(f"{sport.name}: {len(missing)} categories {'would be added' if dry_run else 'added'}.")
        self.stdout.write(self.style.SUCCESS(
            f"{'Dry run: would add' if dry_run else 'Added'} {total} categories; {skipped} unsupported sports skipped."
        ))

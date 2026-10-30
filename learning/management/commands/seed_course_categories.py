from django.core.management.base import BaseCommand
from django.db import transaction

from learning.category_seeds import seed_course_categories
from learning.models import LearningCategory


class Command(BaseCommand):
    help = "Add missing default course categories without changing existing courses."

    def add_arguments(self, parser):
        parser.add_argument("--database", default="default")

    def handle(self, *args, **options):
        using = options["database"]
        with transaction.atomic(using=using):
            created = seed_course_categories(LearningCategory, using=using)
        self.stdout.write(self.style.SUCCESS(f"Created {created} course categories."))

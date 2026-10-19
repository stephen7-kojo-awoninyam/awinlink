from django.core.management.base import BaseCommand
from django.utils import timezone
from accounts.models import GoogleAuthAttempt


class Command(BaseCommand):
    help = "Delete expired Google authentication attempts, including temporary claims and PKCE secrets."

    def handle(self, *args, **options):
        count, _ = GoogleAuthAttempt.objects.filter(expires_at__lte=timezone.now()).delete()
        self.stdout.write(f"Deleted {count} expired Google authentication attempts.")

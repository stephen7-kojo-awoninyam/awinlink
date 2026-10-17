import json
from django.core.management.base import BaseCommand, CommandError
from messaging.turn import turn_configuration, turn_summary


class Command(BaseCommand):
    help = "Validate production TURN configuration without displaying secrets or contacting a relay."

    def handle(self, *args, **options):
        config = turn_configuration()
        self.stdout.write(json.dumps(turn_summary(config), indent=2))
        if config['errors']:
            raise CommandError('TURN configuration is not production ready. See redacted checks above.')

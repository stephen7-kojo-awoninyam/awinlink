import json

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction

from marketplace.legacy_audit import audit_legacy_marketplace


class Command(BaseCommand):
    help = 'Read-only preflight for Talent Market migration 0002; never repairs or deletes rows.'
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument('--database', default='default')

    def handle(self, *args, **options):
        alias = options['database']
        if alias not in connections:
            raise CommandError('Unknown database alias.')
        with transaction.atomic(using=alias):
            if connections[alias].vendor == 'postgresql':
                with connections[alias].cursor() as cursor:
                    cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            report = audit_legacy_marketplace(apps, using=alias)
        self.stdout.write(json.dumps(report, indent=2))
        if not report['ready']:
            raise CommandError('Migration 0002 blocked by legacy data. Review reported IDs/groups and '
                               'resolve with the data owners; do not fabricate consent or delete deal history. '
                               'Run again with market writes paused before applying the migration.')

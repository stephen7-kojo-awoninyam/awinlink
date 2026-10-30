from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from media_erasure.services import process_due_jobs


class Command(BaseCommand):
    help = 'Recheck retention, holds, references and metadata; never deletes media bytes.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100)

    def handle(self, *args, **options):
        limit = options['limit']
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise CommandError('--limit must be between 1 and 1000')
        jobs = process_due_jobs(limit=limit)
        states = Counter(job.state for job in jobs)
        self.stdout.write(self.style.SUCCESS(
            f'Rechecked {len(jobs)} media erasure jobs: ' + ', '.join(
                f'{state}={count}' for state, count in sorted(states.items())
            )
        ))
        self.stdout.write('No local files or provider assets were deleted.')

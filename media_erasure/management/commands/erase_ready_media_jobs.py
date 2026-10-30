from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from media_erasure.models import MediaErasureJob
from media_erasure.services import erase_ready_jobs, process_due_jobs


class Command(BaseCommand):
    help = 'Recheck retention, holds and references; erasure requires the explicit --apply flag.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100)
        parser.add_argument('--apply', action='store_true', help='Physically erase eligible local or verified Cloudinary media.')
        parser.add_argument('--operator-user-id', type=int, help='Active superuser ID; required with --apply.')

    def handle(self, *args, **options):
        limit = options['limit']
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise CommandError('--limit must be between 1 and 1000')
        if options['apply'] and not options['operator_user_id']:
            raise CommandError('--operator-user-id is required with --apply')
        if options['apply']:
            from django.contrib.auth import get_user_model
            if not get_user_model().objects.filter(pk=options['operator_user_id'],
                    is_active=True, is_superuser=True).exists():
                raise CommandError('An active superuser ID is required with --apply')
        process_due_jobs(limit=limit)
        try:
            results = erase_ready_jobs(apply=options['apply'], limit=limit,
                operator_user_id=options['operator_user_id'])
        except PermissionError as error:
            raise CommandError(str(error)) from error
        counts = Counter(state for _, state, _ in results)
        self.stdout.write('Media erasure review: ' + (', '.join(
            f'{state}={count}' for state, count in sorted(counts.items())
        ) or 'no eligible jobs'))
        if options['apply']:
            erased = sum(1 for _, _, did_erase in results if did_erase)
            self.stdout.write(self.style.SUCCESS(f'Confirmed erasure for {erased} eligible media assets.'))
        else:
            self.stdout.write('Dry run only; no local files or provider assets were deleted. Pass --apply after policy review to erase.')

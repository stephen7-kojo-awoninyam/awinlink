from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from media_erasure.models import MediaErasureJob
from media_erasure.services import verify_cloudinary_identity


class Command(BaseCommand):
    help = 'Read-only verify a queued Cloudinary identity; does not erase assets.'

    def add_arguments(self, parser):
        parser.add_argument('--job-id', type=int, required=True)
        parser.add_argument('--asset-id', required=True)
        parser.add_argument('--resource-type', choices=('image', 'video', 'raw'), required=True)
        parser.add_argument('--delivery-type', choices=('upload', 'private', 'authenticated'), required=True)
        parser.add_argument('--operator-user-id', type=int, required=True)

    def handle(self, *args, **options):
        user_model = get_user_model()
        if not user_model.objects.filter(pk=options['operator_user_id'], is_active=True, is_superuser=True).exists():
            raise CommandError('An active superuser ID is required.')
        try:
            job = MediaErasureJob.objects.get(pk=options['job_id'])
            verify_cloudinary_identity(job, asset_id=options['asset_id'], resource_type=options['resource_type'],
                delivery_type=options['delivery_type'], verified_by_id=options['operator_user_id'])
        except (MediaErasureJob.DoesNotExist, ValueError, PermissionError) as error:
            raise CommandError('The queued Cloudinary identity was not verified.') from error
        self.stdout.write(self.style.SUCCESS(f'Verified provider identity for queue job {job.pk}; no asset was deleted.'))

import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.core.files.storage import FileSystemStorage
from django.test import TestCase, override_settings
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from portfolio.models import PortfolioItem
from talents.models import TalentProfile
from .models import MediaErasureJob, MediaLegalHold
from .services import (RETENTION_DAYS, delete_instance_with_retention, enqueue_instance_media,
                       erase_ready_jobs, place_legal_hold, process_due_jobs, release_legal_hold,
                       verify_cloudinary_identity)


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class MediaErasureQueueTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='awinlink-erasure-')
        self.addCleanup(self.directory.cleanup)
        override = override_settings(MEDIA_ROOT=self.directory.name)
        override.enable(); self.addCleanup(override.disable)
        self.owner = User.objects.create_user('retention-owner')
        self.admin = User.objects.create_user('retention-admin')
        self.admin.is_superuser = True
        self.admin.save(update_fields=['is_superuser'])
        self.talent = TalentProfile.objects.create(user=self.owner)
        self.storage = FileSystemStorage()

    def portfolio(self, *, file_name='portfolio/files/retained.pdf', image_name='portfolio/images/retained.png'):
        return PortfolioItem.objects.create(talent=self.talent, title='Retained work', item_type='DOCUMENT',
            file=file_name, image=image_name)

    def test_delete_queues_every_file_field_with_exactly_thirty_day_retention(self):
        item = self.portfolio()
        requested_at = timezone.now()
        with patch('media_erasure.services.timezone.now', return_value=requested_at):
            jobs = delete_instance_with_retention(item, requested_by_id=self.owner.pk)
        self.assertEqual({job.source_field for job in jobs}, {'file', 'image'})
        self.assertEqual(MediaErasureJob.objects.count(), 2)
        for job in jobs:
            self.assertEqual(job.retain_until, requested_at + timedelta(days=30))
            self.assertEqual(job.source_model, 'portfolio.portfolioitem')
            self.assertEqual(job.requested_by_id, self.owner.pk)
            self.assertFalse(PortfolioItem.objects.filter(pk=item.pk).exists())

    def test_due_local_job_becomes_ready_without_erasing_bytes(self):
        item = self.portfolio()
        file_name = item.file.name
        job = delete_instance_with_retention(item)[0]
        path = Path(self.directory.name) / file_name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('wb') as retained:
            retained.write(b'keep until a separately approved erasure executor runs')
        before = process_due_jobs(now=job.retain_until - timedelta(microseconds=1))
        self.assertEqual(before[0].state, MediaErasureJob.State.PENDING)
        due = process_due_jobs(now=job.retain_until)
        self.assertEqual(due[0].state, MediaErasureJob.State.READY)
        self.assertEqual(due[0].last_reason, 'eligible_no_deletion_performed')
        self.assertTrue(self.storage.exists(file_name))

    def test_erasure_defaults_to_dry_run_and_apply_uses_isolated_storage_delete(self):
        item = self.portfolio(file_name='portfolio/files/apply.pdf', image_name='')
        job = delete_instance_with_retention(item)[0]
        process_due_jobs(now=job.retain_until)
        preview = erase_ready_jobs(now=job.retain_until)
        self.assertEqual(preview, [(job.pk, MediaErasureJob.State.READY, False)])
        self.assertEqual(MediaErasureJob.objects.get(pk=job.pk).state, MediaErasureJob.State.READY)
        with patch('media_erasure.services.FileSystemStorage.delete') as delete:
            applied = erase_ready_jobs(apply=True, now=job.retain_until, operator_user_id=self.admin.pk)
        self.assertEqual(applied, [(job.pk, MediaErasureJob.State.ERASED, True)])
        delete.assert_called_once_with('portfolio/files/apply.pdf')
        job.refresh_from_db()
        self.assertEqual(job.erased_by_id, self.admin.pk)
        self.assertEqual(job.erased_at, job.last_checked_at)

    def test_physical_erasure_requires_an_active_superuser(self):
        item = self.portfolio(file_name='portfolio/files/admin-only.pdf', image_name='')
        job = delete_instance_with_retention(item)[0]
        process_due_jobs(now=job.retain_until)
        with patch('media_erasure.services.FileSystemStorage.delete') as delete:
            with self.assertRaises(PermissionError):
                erase_ready_jobs(apply=True, now=job.retain_until, operator_user_id=self.owner.pk)
        delete.assert_not_called()
        self.assertEqual(MediaErasureJob.objects.get(pk=job.pk).state, MediaErasureJob.State.READY)

    def test_apply_rechecks_new_legal_holds_and_shared_references(self):
        item = self.portfolio(file_name='portfolio/files/rechecked.pdf', image_name='')
        job = delete_instance_with_retention(item)[0]
        process_due_jobs(now=job.retain_until)
        hold = place_legal_hold(job.storage_name, reason='Preservation order', placed_by_id=self.admin.pk)
        with patch('media_erasure.services.FileSystemStorage.delete') as delete:
            held = erase_ready_jobs(apply=True, now=job.retain_until, operator_user_id=self.admin.pk)
        self.assertEqual(held[0][1], MediaErasureJob.State.HELD)
        delete.assert_not_called()
        release_legal_hold(hold.pk, released_by_id=self.admin.pk)
        PortfolioItem.objects.create(talent=self.talent, title='Shared again', item_type='DOCUMENT',
            file=job.storage_name)
        with patch('media_erasure.services.FileSystemStorage.delete') as delete:
            shared = erase_ready_jobs(apply=True, now=job.retain_until, operator_user_id=self.admin.pk)
        self.assertEqual(shared[0][1], MediaErasureJob.State.SHARED)
        delete.assert_not_called()

    @override_settings(STORAGES={
        'default': {'BACKEND': 'config.media_storage.PlaybackMediaStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }, CLOUDINARY_STORAGE={'CLOUD_NAME': 'fixture', 'API_KEY': 'fixture', 'API_SECRET': 'fixture'})
    def test_apply_uses_verified_cloudinary_identity_without_live_provider_call(self):
        from config.media_storage import PlaybackMediaStorage
        item = self.portfolio(file_name='portfolio/files/apply-cloud.pdf', image_name='')
        job = delete_instance_with_retention(item)[0]
        job.resource_type = 'raw'; job.delivery_type = 'upload'; job.provider_asset_id = 'fixture-asset'
        job.identity_verified_at = timezone.now(); job.provider_cloud_name = 'fixture'
        job.save(update_fields=('resource_type', 'delivery_type', 'provider_asset_id', 'identity_verified_at', 'provider_cloud_name'))
        process_due_jobs(now=job.retain_until)
        with patch.object(PlaybackMediaStorage, 'delete_asset', return_value=True) as delete_asset:
            result = erase_ready_jobs(apply=True, now=job.retain_until, operator_user_id=self.admin.pk)
        self.assertEqual(result, [(job.pk, MediaErasureJob.State.ERASED, True)])
        delete_asset.assert_called_once_with(job.storage_name, asset_id='fixture-asset',
            resource_type='raw', delivery_type='upload')

    def test_legal_hold_blocks_due_job_until_audited_release(self):
        item = self.portfolio(image_name='portfolio/images/held.png')
        job = next(row for row in delete_instance_with_retention(item) if row.source_field == 'image')
        hold = place_legal_hold(job.storage_name, reason='Active legal matter', placed_by_id=self.admin.pk)
        held = next(row for row in process_due_jobs(now=job.retain_until) if row.pk == job.pk)
        self.assertEqual(held.state, MediaErasureJob.State.HELD)
        self.assertEqual(held.last_reason, 'active_legal_hold')
        released = release_legal_hold(hold.pk, released_by_id=self.admin.pk)
        self.assertFalse(released.held)
        self.assertIsNotNone(released.released_at)
        ready = next(row for row in process_due_jobs(now=job.retain_until) if row.pk == job.pk)
        self.assertEqual(ready.state, MediaErasureJob.State.READY)

    def test_shared_reference_and_latest_reference_retention_both_block_erasure(self):
        first = self.portfolio(file_name='portfolio/files/shared.pdf', image_name='')
        second = self.portfolio(file_name='portfolio/files/shared.pdf', image_name='')
        start = timezone.now()
        with patch('media_erasure.services.timezone.now', return_value=start):
            first_job = delete_instance_with_retention(first)[0]
        self.assertEqual(process_due_jobs(now=first_job.retain_until)[0].state, MediaErasureJob.State.SHARED)

        later = start + timedelta(days=10)
        with patch('media_erasure.services.timezone.now', return_value=later):
            second_job = delete_instance_with_retention(second)[0]
        at_first_expiry = process_due_jobs(now=first_job.retain_until)
        self.assertEqual({job.state for job in at_first_expiry}, {MediaErasureJob.State.PENDING})
        self.assertEqual(max(job.retain_until for job in at_first_expiry), later + timedelta(days=30))
        self.assertLess(first_job.retain_until, second_job.retain_until)
        at_last_expiry = process_due_jobs(now=second_job.retain_until)
        self.assertEqual({job.state for job in at_last_expiry}, {MediaErasureJob.State.READY})

    def test_duplicate_enqueue_is_idempotent(self):
        item = self.portfolio(image_name='')
        first = enqueue_instance_media(item)
        second = enqueue_instance_media(item)
        self.assertEqual([row.pk for row in first], [row.pk for row in second])
        self.assertEqual(MediaErasureJob.objects.count(), 1)

    def test_database_rollback_removes_queue_entry_and_keeps_source_record(self):
        item = self.portfolio(image_name='')
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                delete_instance_with_retention(item, requested_by_id=self.owner.pk)
                raise RuntimeError('rollback fixture')
        self.assertTrue(PortfolioItem.objects.filter(pk=item.pk).exists())
        self.assertFalse(MediaErasureJob.objects.exists())

    @override_settings(STORAGES={
        'default': {'BACKEND': 'config.media_storage.PlaybackMediaStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }, CLOUDINARY_STORAGE={'CLOUD_NAME': 'fixture', 'API_KEY': 'fixture', 'API_SECRET': 'fixture'})
    def test_legacy_cloudinary_delivery_stays_unresolved_until_exact_asset_metadata_is_verified(self):
        item = self.portfolio(file_name='portfolio/files/legacy.pdf', image_name='')
        job = delete_instance_with_retention(item)[0]
        self.assertEqual(job.storage_kind, 'CLOUDINARY')
        self.assertEqual(job.resource_type, '')
        self.assertEqual(job.delivery_type, '')
        unresolved = process_due_jobs(now=job.retain_until)[0]
        self.assertEqual(unresolved.state, MediaErasureJob.State.UNRESOLVED)

        from django.core.files.storage import default_storage
        public_id = default_storage._prepend_prefix(job.storage_name)
        with patch('cloudinary.api.resource', return_value={'asset_id': 'legacy-id', 'public_id': public_id}) as resource:
            verify_cloudinary_identity(job, asset_id='legacy-id', resource_type='raw', delivery_type='upload',
                verified_by_id=self.admin.pk)
        resource.assert_called_once_with(public_id, resource_type='raw', type='upload')
        ready = process_due_jobs(now=job.retain_until)[0]
        self.assertEqual(ready.state, MediaErasureJob.State.READY)
        self.assertEqual(ready.delivery_type, 'upload')
        self.assertIsNotNone(ready.identity_verified_at)

    @override_settings(STORAGES={
        'default': {'BACKEND': 'config.media_storage.PlaybackMediaStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }, CLOUDINARY_STORAGE={'CLOUD_NAME': 'fixture', 'API_KEY': 'fixture', 'API_SECRET': 'fixture'})
    def test_non_superuser_cannot_trigger_cloudinary_metadata_lookup(self):
        item = self.portfolio(file_name='portfolio/files/no-look.pdf', image_name='')
        job = delete_instance_with_retention(item)[0]
        with patch('cloudinary.api.resource') as resource:
            with self.assertRaises(PermissionError):
                verify_cloudinary_identity(job, asset_id='x', resource_type='raw', delivery_type='upload',
                    verified_by_id=self.owner.pk)
        resource.assert_not_called()

    def test_unverified_provider_ids_and_bad_queue_limits_fail_closed(self):
        item = self.portfolio(file_name='portfolio/files/unresolved.pdf', image_name='')
        job = delete_instance_with_retention(item)[0]
        job.storage_kind = 'CLOUDINARY'; job.save(update_fields=['storage_kind'])
        with self.assertRaises(ValueError):
            process_due_jobs(limit=0)
        due = process_due_jobs(now=job.retain_until)[0]
        self.assertEqual(due.state, MediaErasureJob.State.UNRESOLVED)
        self.assertEqual(MediaLegalHold.objects.count(), 0)

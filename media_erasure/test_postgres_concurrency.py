from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

from django.db import close_old_connections
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from accounts.models import User
from portfolio.models import PortfolioItem
from talents.models import TalentProfile
from .models import MediaErasureJob
from .services import delete_instance_with_retention, enqueue_instance_media, process_due_jobs


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class MediaErasurePostgresConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        user = User.objects.create_user('media-queue-concurrent')
        talent = TalentProfile.objects.create(user=user)
        self.item = PortfolioItem.objects.create(talent=talent, title='Concurrent media', item_type='DOCUMENT',
            file='portfolio/files/concurrent.pdf')

    def test_concurrent_duplicate_enqueue_creates_one_durable_job(self):
        barrier = Barrier(2)
        item_id = self.item.pk

        def enqueue():
            close_old_connections()
            try:
                item = PortfolioItem.objects.get(pk=item_id)
                barrier.wait(timeout=10)
                return [job.pk for job in enqueue_instance_media(item)]
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(lambda _: enqueue(), range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(MediaErasureJob.objects.count(), 1)

    def test_concurrent_workers_claim_each_due_job_once_and_never_delete(self):
        first = delete_instance_with_retention(self.item)[0]
        second = MediaErasureJob.objects.create(storage_name=first.storage_name, storage_kind='LOCAL',
            source_model='events.eventmedia', source_pk='88', source_field='file', requested_at=first.requested_at,
            retain_until=first.retain_until)
        due = max(first.retain_until, second.retain_until) + timedelta(seconds=1)
        barrier = Barrier(2)

        def process():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return [job.pk for job in process_due_jobs(limit=1, now=due)]
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(lambda _: process(), range(2)))
        handled = [job_id for group in results for job_id in group]
        self.assertEqual(set(handled), {first.pk, second.pk})
        self.assertEqual(len(handled), 2)
        self.assertEqual(set(MediaErasureJob.objects.values_list('state', flat=True)), {MediaErasureJob.State.READY})

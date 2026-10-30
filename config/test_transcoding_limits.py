from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from .media_transcoding import playback_copy
from .resource_limits import ResourceLimited


class TranscodingLimitTests(SimpleTestCase):
    def test_duplicate_work_is_rejected_and_failed_producer_releases_leases(self):
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            source = Path(directory) / 'source.mov'; source.write_bytes(b'original bytes')
            started, finish = threading.Event(), threading.Event()
            def produce(*args):
                started.set()
                if not finish.wait(5): raise AssertionError('Producer test timed out')
                raise RuntimeError('FFmpeg fixture failure')
            with patch('config.media_transcoding._produce', side_effect=produce) as producer, ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(playback_copy, source, 'mp4')
                try:
                    self.assertTrue(started.wait(5))
                    with self.assertRaises(ResourceLimited): playback_copy(source, 'mp4')
                    self.assertEqual(producer.call_count, 1)
                finally: finish.set()
                with self.assertRaises(RuntimeError): future.result(timeout=5)
            target = Path(directory) / 'cached.mp4'
            with patch('config.media_transcoding._produce', return_value=target) as producer:
                self.assertEqual(playback_copy(source, 'mp4'), target)
                producer.assert_called_once()
            self.assertEqual(source.read_bytes(), b'original bytes')

    def test_cluster_capacity_bounds_different_files_and_cached_files_need_no_slot(self):
        from .resource_limits import Lease
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            source = Path(directory) / 'source.mov'; source.write_bytes(b'original bytes')
            held = [Lease('transcoding', 'cluster').acquire() for _ in range(2)]
            try:
                with self.assertRaises(ResourceLimited): playback_copy(source, 'mp4')
            finally:
                for lease in held: lease.release()
            def produce(source, media_format, cache, target): target.write_bytes(b'derivative'); return target
            with patch('config.media_transcoding._produce', side_effect=produce) as producer:
                target = playback_copy(source, 'mp4')
                with patch('config.media_transcoding.Lease', side_effect=AssertionError('Cached file starts no work')):
                    self.assertEqual(playback_copy(source, 'mp4'), target)
                self.assertEqual(producer.call_count, 1)

"""Cross-process assertions; only the explicit disposable fixture is accepted."""
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest import skipUnless
from uuid import uuid4

from django.test import SimpleTestCase, override_settings

from .resource_limits import Lease, ResourceLimited, consume


@skipUnless(os.environ.get('AWINLINK_SECURITY_TEST_REDIS_URL'), 'Requires the isolated Redis test runner.')
class SharedResourceRedisTests(SimpleTestCase):
    def race(self, mode):
        root = Path(__file__).resolve().parents[1]
        run = uuid4().hex
        processes = [subprocess.Popen([sys.executable, '-B', str(root / 'scripts/resource_limit_worker.py'), mode, run],
            cwd=root, env=os.environ.copy(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0) for _ in range(2)]
        reports = []
        try:
            for process in processes:
                output, errors = process.communicate(timeout=75)
                self.assertEqual(process.returncode, 0, errors[-1500:])
                reports.append(json.loads(output))
        finally:
            for process in processes:
                if process.poll() is None: process.terminate(); process.wait(timeout=5)
        self.assertEqual(sum(report['allowed'] for report in reports), 3, reports)
        self.assertEqual(sum(report['limited'] for report in reports), 17, reports)

    def test_byte_budget_is_atomic_across_workers(self):
        self.race('bytes')

    def test_connection_leases_cannot_be_oversubscribed_across_workers(self):
        self.race('slots')

    def test_redis_lease_fencing_expiry_and_retry_after(self):
        import time
        url = os.environ['AWINLINK_SECURITY_TEST_REDIS_URL']
        prefix = os.environ['AWINLINK_SECURITY_TEST_PREFIX']
        with override_settings(CACHES={'resource_fixture': {'BACKEND': 'django.core.cache.backends.redis.RedisCache',
                'LOCATION': url, 'KEY_PREFIX': prefix}}, AWINLINK_RESOURCE_CACHE_ALIAS='resource_fixture',
                AWINLINK_RESOURCE_LIMITS={'expiry_slots': (1, 1), 'small_bytes': (10, 3600)}):
            identity = uuid4().hex
            old = Lease('expiry_slots', identity).acquire()
            with self.assertRaises(ResourceLimited): Lease('expiry_slots', identity).acquire()
            time.sleep(1.1)
            replacement = Lease('expiry_slots', identity).acquire()
            with self.assertRaises(ResourceLimited): old.renew()
            old.release()
            with self.assertRaises(ResourceLimited): Lease('expiry_slots', identity).acquire()
            replacement.renew(); replacement.release()
            consume('small_bytes', identity, 10)
            with self.assertRaises(ResourceLimited) as raised: consume('small_bytes', identity, 1)
            self.assertGreaterEqual(raised.exception.wait, 359)

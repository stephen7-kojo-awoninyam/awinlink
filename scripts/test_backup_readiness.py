from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.check_backup_readiness import BACKUP_QUERY, BackupCheckUnavailable, backup_metadata, summarize, pitr_metadata


class BackupReadinessTests(unittest.TestCase):
    def test_empty_backups_and_schedules_are_blocked(self):
        report = summarize({'backups': [], 'schedules': []}, datetime.now(timezone.utc))
        self.assertEqual(report['status'], 'BLOCKED')
        self.assertFalse(report['fresh_backup_within_24_hours'])
        self.assertEqual(len(report['blockers']), 3)

    @patch('scripts.check_backup_readiness.subprocess.run')
    def test_only_fixed_read_query_is_sent_and_partial_errors_are_not_clean(self, run):
        run.return_value = SimpleNamespace(returncode=0, stdout='{"errors":[{"message":"private detail"}],"data":{"backups":[],"schedules":[]}}')
        with self.assertRaises(BackupCheckUnavailable):
            backup_metadata('fixture-volume')
        self.assertEqual(run.call_args.kwargs['input'], BACKUP_QUERY)
        self.assertTrue(BACKUP_QUERY.startswith('query '))
        self.assertNotIn('mutation', BACKUP_QUERY.lower())

    def test_backup_metadata_does_not_prove_a_restore(self):
        now = datetime.now(timezone.utc)
        report = summarize({'backups': [{'createdAt': now.isoformat(), 'expiresAt': None}], 'schedules': [{'kind': 'DAILY'}]}, now)
        self.assertTrue(report['fresh_backup_within_24_hours'])
        self.assertFalse(report['restore_verified'])
        self.assertEqual(report['status'], 'BLOCKED')

    def test_invalid_backup_timestamps_are_inconclusive(self):
        with self.assertRaises(BackupCheckUnavailable):
            summarize({'backups': [{'createdAt': 'invalid'}], 'schedules': []}, datetime.now(timezone.utc))

    @patch('scripts.check_backup_readiness.subprocess.run')
    def test_pitr_only_reads_status_and_withholds_failed_command_details(self, run):
        run.return_value = SimpleNamespace(returncode=0, stdout='{"enabled":false,"bucketWired":false}')
        self.assertEqual(pitr_metadata()['pitr_status'], 'disabled')
        self.assertEqual(run.call_args.args[0][-2:], ['pitr', 'status'])
        run.return_value = SimpleNamespace(returncode=1, stdout='private credentials')
        self.assertEqual(pitr_metadata(), {'pitr_status': 'inconclusive'})

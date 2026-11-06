"""Exercise the pending expansion with real historical reporting writers."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class ReportingMigrationTests(TransactionTestCase):
    old = [('accounts', '0007_google_auth'),
           ('learning', '0017_optional_course_modules'),
           ('messaging', '0014_retire_legacy_call_statuses')]

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def test_pending_graph_preserves_reports_and_supports_both_writers(self):
        latest = MigrationExecutor(connection).loader.graph.leaf_nodes()
        self.addCleanup(self.migrate, latest)
        old = self.migrate(self.old)
        Report = old.get_model('accounts', 'ContentReport')
        user = old.get_model('accounts', 'User').objects.create(username='legacy-reporter')
        original = Report.objects.create(reporter_id=user.pk, target_type='user',
                                         target_id=user.pk, reason='spam', details='Keep this report')
        original_values = Report.objects.values().get(pk=original.pk)
        executor = MigrationExecutor(connection)
        pending = {migration.name for migration, backwards in executor.migration_plan(latest)}
        self.assertTrue({'0008_age_aware_accounts', '0009_age_safety_permissions',
                         '0010_google_deletion_reauthentication', '0011_child_safety_reporting',
                         '0018_age_safety_permissions', '0015_callparticipant_is_guest'} <= pending)
        current = self.migrate(latest)
        NewReport = current.get_model('accounts', 'ContentReport')
        self.assertEqual(NewReport.objects.get(pk=original.pk).contact_email, '')
        # Historical ORM INSERT omits contact_email, just like a running old worker.
        legacy = Report.objects.create(reporter_id=user.pk, target_type='user',
                                       target_id=user.pk, reason='other', details='Old worker')
        self.assertEqual(NewReport.objects.get(pk=legacy.pk).contact_email, '')
        from accounts.models import ContentReport
        self.assertEqual(ContentReport().contact_email, '')
        omitted = ContentReport.objects.create(target_type='safety', target_id=0,
                                               reason='child_safety', details='Anonymous concern')
        explicit = ContentReport.objects.create(target_type='safety', target_id=0,
                                                reason='child_safety', details='Contact concern',
                                                contact_email='reply@example.com')
        omitted.refresh_from_db()
        self.assertEqual(omitted.contact_email, '')
        explicit.refresh_from_db()
        self.assertEqual(explicit.contact_email, 'reply@example.com')
        event = current.get_model('accounts', 'ReportReviewEvent').objects.create(
            report_id=explicit.pk, actor_id=user.pk, action='REVIEW',
            previous_status='OPEN', new_status='REVIEWED', notes='Preserve audit')
        # Re-running an already applied plan must not overwrite report/audit data.
        current = self.migrate(latest)
        self.assertEqual(current.get_model('accounts', 'ReportReviewEvent').objects.get(pk=event.pk).notes,
                         'Preserve audit')
        self.assertEqual(ContentReport.objects.get(pk=explicit.pk).contact_email, 'reply@example.com')
        from config.migration_safety import check_reverse_plan
        from django.db.migrations.exceptions import IrreversibleError
        executor = MigrationExecutor(connection)
        with self.assertRaises(IrreversibleError):
            check_reverse_plan(connection, executor.migration_plan(self.old))
        if connection.vendor == 'postgresql':
            with connection.cursor() as cursor:
                cursor.execute("""SELECT column_default, is_nullable FROM information_schema.columns
                                  WHERE table_schema = current_schema()
                                  AND table_name = 'accounts_contentreport'
                                  AND column_name = 'contact_email'""")
                default, nullable = cursor.fetchone()
            self.assertIn("''", default)
            self.assertEqual(nullable, 'NO')
        # Structural reversal preserves report rows and all pre-expansion columns.
        # The new email column/audit table are deliberately lost on schema rollback.
        restored = self.migrate(self.old).get_model('accounts', 'ContentReport')
        self.assertEqual(restored.objects.values().get(pk=original.pk), original_values)
        self.assertEqual(restored.objects.count(), 4)
        self.assertEqual(restored.objects.get(pk=explicit.pk).reason, 'child_safety')
        restored.objects.create(target_type='user', target_id=user.pk, reason='spam')
        self.migrate(latest)
        self.assertEqual(ContentReport.objects.count(), 5)
        self.assertEqual(ContentReport.objects.get(pk=original.pk).details, 'Keep this report')

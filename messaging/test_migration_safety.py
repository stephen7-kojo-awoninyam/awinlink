"""Real PostgreSQL preservation, whole-plan rollback and interrupted DDL tests."""
from unittest import skipUnless
from pathlib import Path
from uuid import uuid4

from django.core.management import call_command, CommandError
from django.db import connection, NotSupportedError
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.exceptions import IrreversibleError
from django.db.migrations.recorder import MigrationRecorder
from django.test import TransactionTestCase, TestCase

from config.migration_safety import SafeMigrationExecutor


@skipUnless(connection.vendor == 'postgresql', 'PostgreSQL catalog and concurrent DDL')
class MigrationSafetyTests(TransactionTestCase):
    def historical(self, targets):
        # Historical migrations are deliberately irreversible. Build a fresh
        # disposable database, rather than bypassing their guards to seed tests.
        import psycopg2
        from psycopg2 import sql
        parameters = connection.get_connection_params()
        parameters['dbname'] = 'postgres'
        admin = psycopg2.connect(**parameters)
        admin.autocommit = True
        with admin.cursor() as cursor:
            cursor.execute('SHOW data_directory')
            root = Path(__file__).resolve().parents[1]
            if Path(cursor.fetchone()[0]).resolve() != (root / '.audit-vc-tools/postgres-data').resolve():
                admin.close()
                self.skipTest('Disposable databases require the verified workspace cluster')
            cursor.execute('SET statement_timeout=900000')
        name = 'awinlink_safety_' + uuid4().hex
        original = connection.settings_dict['NAME']
        with admin.cursor() as cursor:
            cursor.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        connection.close()
        connection.settings_dict['NAME'] = name

        def cleanup():
            connection.close()
            connection.settings_dict['NAME'] = original
            try:
                with admin.cursor() as cursor:
                    cursor.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))
            finally:
                admin.close()

        self.addCleanup(cleanup)
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def test_legacy_membership_and_call_decisions_survive(self):
        state = self.historical([('messaging', '0005_message_video')])
        User = state.get_model('accounts', 'User')
        owner, talent, outsider = [User.objects.create(username=name) for name in ['owner', 'talent', 'outsider']]
        org = state.get_model('organizations', 'Organization').objects.create(user_id=owner.pk, name='Legacy club')
        profile = state.get_model('talents', 'TalentProfile').objects.create(user_id=talent.pk)
        room = state.get_model('messaging', 'Conversation').objects.create(organization_id=org.pk, talent_id=profile.pk)
        # An author is not automatically entitled to become a participant.
        message = state.get_model('messaging', 'Message').objects.create(conversation_id=room.pk, sender_id=outsider.pk, content='Keep')
        target = [('messaging', '0009_conversation_created_by_conversation_image_and_more')]
        executor = MigrationExecutor(connection)
        executor.migrate(target)
        state = executor.loader.project_state(target).apps
        members = state.get_model('messaging', 'ConversationParticipant')
        self.assertEqual(set(members.objects.filter(conversation_id=room.pk).values_list('user_id', flat=True)), {owner.pk, talent.pk})
        self.assertEqual(state.get_model('messaging', 'Message').objects.get(pk=message.pk).content, 'Keep')
        Call = state.get_model('messaging', 'Call')
        ids = {}
        timestamps = {}
        for status in ['ACCEPTED', 'REJECTED', 'ENDED', 'RINGING', 'MISSED']:
            call = Call.objects.create(conversation_id=room.pk, caller_id=owner.pk, receiver_id=talent.pk, status=status, call_type='VOICE')
            ids[status] = call.pk
            timestamps[call.pk] = (call.started_at, call.answered_at, call.ended_at, call.duration)
        executor = MigrationExecutor(connection)
        latest = [('messaging', '0014_retire_legacy_call_statuses')]
        executor.migrate(latest)
        current = executor.loader.project_state(latest).apps
        for old, pk in ids.items():
            call = current.get_model('messaging', 'Call').objects.get(pk=pk)
            self.assertEqual(call.status, 'ENDED' if old in ['ACCEPTED', 'REJECTED'] else old)
            self.assertEqual(call.legacy_status, old if old in ['ACCEPTED', 'REJECTED'] else '')
            self.assertEqual((call.started_at, call.answered_at, call.ended_at, call.duration), timestamps[pk])
            self.assertEqual(set(call.participants.values_list('user_id', flat=True)), {owner.pk, talent.pk})
        before = set(MigrationRecorder(connection).applied_migrations())
        with self.assertRaises(IrreversibleError):
            SafeMigrationExecutor(connection).migrate([('messaging', '0005_message_video')])
        self.assertEqual(set(MigrationRecorder(connection).applied_migrations()), before)

    def test_applied_legacy_status_repair_preserves_modern_active_call(self):
        state = self.historical([('messaging', '0013_resource_pagination_indexes')])
        users = [state.get_model('accounts', 'User').objects.create(username=name) for name in ['caller', 'receiver']]
        room = state.get_model('messaging', 'Conversation').objects.create()
        calls = []
        for status in ['ACCEPTED', 'REJECTED', 'ACTIVE']:
            call = state.get_model('messaging', 'Call').objects.create(conversation_id=room.pk, initiated_by_id=users[0].pk, status=status, call_type='VOICE')
            for user, participant_status in zip(users, ['JOINED', 'RINGING']):
                state.get_model('messaging', 'CallParticipant').objects.create(call_id=call.pk, user_id=user.pk, status=participant_status)
            calls.append(call)
        executor = MigrationExecutor(connection)
        latest = [('messaging', '0014_retire_legacy_call_statuses')]
        executor.migrate(latest)
        current = executor.loader.project_state(latest).apps
        self.assertEqual(list(current.get_model('messaging', 'Call').objects.order_by('pk').values_list('status', 'legacy_status')),
                         [('ENDED', 'ACCEPTED'), ('ENDED', 'REJECTED'), ('ACTIVE', '')])
        self.assertEqual(list(current.get_model('messaging', 'CallParticipant').objects.filter(call_id=calls[-1].pk).order_by('pk').values_list('status', flat=True)), ['JOINED', 'RINGING'])
        # Never infer missing private membership from participants or authors.
        self.assertFalse(current.get_model('messaging', 'ConversationParticipant').objects.exists())

    def test_whole_plan_guard_precedes_dependent_analytics_reversal(self):
        from accounts.models import User
        from coaches.models import CoachProfile
        from organizations.models import Organization, OrganizationTalent
        user = User.objects.create(username='coach-owner')
        org = Organization.objects.create(user=user, name='Guard club')
        coach = CoachProfile.objects.create(user=user)
        OrganizationTalent.objects.create(organization=org, coach=coach, name='Coach', tag='Coach', status='REMOVED')
        before = set(MigrationRecorder(connection).applied_migrations())
        with self.assertRaises(IrreversibleError):
            call_command('migrate', 'organizations', '0013_roster_agreements', verbosity=0, interactive=False)
        self.assertEqual(set(MigrationRecorder(connection).applied_migrations()), before)
        self.assertIn(('analytics', '0005_resource_pagination_indexes'), before)

    def test_concurrent_index_forward_reverse_retries_and_collision(self):
        target = [('learning', '0014_seed_course_categories')]
        state = self.historical(target)
        user = state.get_model('accounts', 'User').objects.create(username='index-owner')
        category = state.get_model('learning', 'LearningCategory').objects.get(name='Sports')
        course = state.get_model('learning', 'Course').objects.create(creator_id=user.pk, category_id=category.pk,
            title='Course', slug='retry-course')
        lesson = state.get_model('learning', 'Lesson').objects.create(course_id=course.pk, title='Keep', order=1)
        destination = [('learning', '0015_resource_pagination_indexes')]
        creates = 0

        def interrupt(execute, sql, params, many, context):
            nonlocal creates
            if str(sql).upper().startswith('CREATE INDEX CONCURRENTLY'):
                creates += 1
                if creates == 2:
                    raise RuntimeError('Synthetic interruption')
            return execute(sql, params, many, context)

        with self.assertRaises(RuntimeError), connection.execute_wrapper(interrupt):
            MigrationExecutor(connection).migrate(destination)
        self.assertNotIn(('learning', '0015_resource_pagination_indexes'), MigrationRecorder(connection).applied_migrations())
        MigrationExecutor(connection).migrate(destination)  # Exact committed index reused.
        drops = 0

        def interrupt_drop(execute, sql, params, many, context):
            nonlocal drops
            if str(sql).upper().startswith('DROP INDEX CONCURRENTLY'):
                drops += 1
                if drops == 2:
                    raise RuntimeError('Synthetic reverse interruption')
            return execute(sql, params, many, context)

        with self.assertRaises(RuntimeError), connection.execute_wrapper(interrupt_drop):
            MigrationExecutor(connection).migrate(target)
        MigrationExecutor(connection).migrate(target)  # Already-dropped index tolerated.
        with connection.cursor() as cursor:
            cursor.execute('CREATE INDEX learning_lesson_page_idx ON learning_lesson (title)')
        try:
            with self.assertRaises(NotSupportedError):
                MigrationExecutor(connection).migrate(destination)
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_get_indexdef('learning_lesson_page_idx'::regclass)")
                self.assertIn('(title)', cursor.fetchone()[0])
        finally:
            with connection.cursor() as cursor:
                cursor.execute('DROP INDEX learning_lesson_page_idx')
        for definition in ['(course_id DESC, "order", id)', '(course_id, "order", id) WHERE id > 0',
                           '(course_id, "order", id) INCLUDE (title)']:
            with connection.cursor() as cursor:
                cursor.execute('CREATE INDEX learning_lesson_page_idx ON learning_lesson ' + definition)
            try:
                with self.assertRaises(NotSupportedError):
                    MigrationExecutor(connection).migrate(destination)
            finally:
                with connection.cursor() as cursor:
                    cursor.execute('DROP INDEX learning_lesson_page_idx')
        # Real canceled concurrent build: another transaction holds a writer.
        import psycopg2
        blocker = psycopg2.connect(**connection.get_connection_params())
        try:
            with blocker.cursor() as cursor:
                cursor.execute('UPDATE learning_lesson SET title=title WHERE id=%s', [lesson.pk])
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout='250ms'")
                try:
                    cursor.execute('CREATE INDEX CONCURRENTLY learning_lesson_page_idx ON learning_lesson (course_id, "order", id)')
                except Exception:
                    pass
                else:
                    self.fail('Expected a blocked concurrent index build')
                finally:
                    cursor.execute("SET lock_timeout='2s'")
                cursor.execute("SELECT indisvalid FROM pg_index WHERE indexrelid='learning_lesson_page_idx'::regclass")
                self.assertFalse(cursor.fetchone()[0])
        finally:
            blocker.rollback()
            blocker.close()
        MigrationExecutor(connection).migrate(destination)
        self.assertEqual(state.get_model('learning', 'Lesson').objects.get(pk=lesson.pk).title, 'Keep')
        with connection.cursor() as cursor:
            cursor.execute("SELECT indisvalid, indisready FROM pg_index WHERE indexrelid='learning_lesson_page_idx'::regclass")
            self.assertEqual(cursor.fetchone(), (True, True))
        from django.db import models
        from config.migration_operations import OnlineIndex
        operation = OnlineIndex('lesson', models.Index(fields=['-course', '-id'], name='safety_desc_retry_idx'))
        migration_state = MigrationExecutor(connection).loader.project_state(destination)
        with connection.schema_editor(atomic=False) as editor:
            operation.database_forwards('learning', editor, migration_state, migration_state)
            operation.database_forwards('learning', editor, migration_state, migration_state)
            operation.database_backwards('learning', editor, migration_state, migration_state)
            operation.database_backwards('learning', editor, migration_state, migration_state)


class LegacyMembershipManifestTests(TestCase):
    def setUp(self):
        import tempfile
        from accounts.models import User
        from messaging.models import Conversation
        self.users = [User.objects.create(username=name) for name in ['first', 'second', 'outsider']]
        self.room = Conversation.objects.create()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'reviewed-manifest.json'

    def manifest(self, rooms=None):
        import json
        self.path.write_text(json.dumps({'source_backup_sha256': 'a' * 64,
            'rooms': rooms if rooms is not None else [{'conversation_id': self.room.pk, 'user_ids': [user.pk for user in self.users[:2]]}]}))

    def run_command(self, apply=False):
        from io import StringIO
        call_command('restore_legacy_conversation_members', str(self.path), apply=apply, stdout=StringIO())

    def test_dry_run_apply_and_idempotency(self):
        from messaging.models import ConversationParticipant
        self.manifest()
        self.run_command()
        self.assertFalse(ConversationParticipant.objects.exists())
        self.run_command(apply=True)
        self.run_command(apply=True)
        self.assertEqual(set(self.room.participants.values_list('user_id', flat=True)), {user.pk for user in self.users[:2]})

    def test_conflict_refuses_all_rooms_and_never_overwrites_membership(self):
        from messaging.models import Conversation, ConversationParticipant
        other = Conversation.objects.create()
        ConversationParticipant.objects.create(conversation=other, user=self.users[2])
        self.manifest([{'conversation_id': self.room.pk, 'user_ids': [self.users[0].pk]},
                       {'conversation_id': other.pk, 'user_ids': [self.users[1].pk]}])
        with self.assertRaises(CommandError):
            self.run_command(apply=True)
        self.assertFalse(self.room.participants.exists())
        self.assertEqual(list(other.participants.values_list('user_id', flat=True)), [self.users[2].pk])

    def test_duplicate_or_unknown_identifiers_refused(self):
        for users in [[self.users[0].pk, self.users[0].pk], [999999999], [True]]:
            self.manifest([{'conversation_id': self.room.pk, 'user_ids': users}])
            with self.assertRaises(CommandError):
                self.run_command(apply=True)
        self.assertFalse(self.room.participants.exists())

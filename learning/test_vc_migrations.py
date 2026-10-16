"""Execute the classroom upgrade chain, preserving representative 0008 records."""
from datetime import timedelta
from uuid import uuid4

from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class VCMigrationChainTests(TransactionTestCase):
    def migrate(self, name):
        executor = MigrationExecutor(connection)
        target = [('learning', name)]
        executor.migrate(target)
        return executor.loader.project_state(target).apps

    def test_incremental_0008_to_0013_preserves_legacy_attendance_and_constraints(self):
        latest = MigrationExecutor(connection).loader.graph.leaf_nodes('learning')
        try:
            old = self.migrate('0008_classroom_live_sessions')
            User = old.get_model(*settings.AUTH_USER_MODEL.split('.'))
            user = User.objects.create(username='vc-upgrade-host', role='COACH')
            category = old.get_model('learning', 'LearningCategory').objects.create(name='VC migration art')
            course = old.get_model('learning', 'Course').objects.create(creator_id=user.pk, category=category,
                title='Art', slug='vc-upgrade-art', description='Art', status='APPROVED')
            lesson = old.get_model('learning', 'Lesson').objects.create(course=course, title='Lines', order=1)
            room = old.get_model('learning', 'Classroom').objects.create(course=course, created_by_id=user.pk, title='Art')
            member = old.get_model('learning', 'ClassroomMembership').objects.create(classroom=room, user_id=user.pk, role='HOST')
            now = timezone.now()
            session = old.get_model('learning', 'LiveSession').objects.create(classroom=room, lesson=lesson,
                title='Art', status='LIVE', started_at=now)
            participant = old.get_model('learning', 'SessionParticipant').objects.create(session=session,
                membership=member, role='HOST', admission_state='ADMITTED', admitted_at=now)
            for index in range(52):
                cohost = User.objects.create(username=f'vc-upgrade-cohost-{index}', role='COACH')
                membership = old.get_model('learning', 'ClassroomMembership').objects.create(
                    classroom=room, user_id=cohost.pk, role='COHOST')
                old.get_model('learning', 'SessionParticipant').objects.create(session=session,
                    membership=membership, role='COHOST', admission_state='ADMITTED', admitted_at=now)
            interval_ids = [old.get_model('learning', 'AttendanceInterval').objects.create(participant=participant,
                joined_at=now + timedelta(minutes=i), left_at=now + timedelta(minutes=i + 1)).pk for i in [0, 2]]
            for name in ['0009_classroom_service_integrity', '0010_classroom_invitations',
                         '0011_classroom_signaling_presence', '0012_session_whiteboards', '0013_classroom_chat']:
                state = self.migrate(name)
                intervals = list(state.get_model('learning', 'AttendanceInterval').objects.filter(pk__in=interval_ids))
                self.assertEqual(len(intervals), 2)
                self.assertEqual(len({row.connection_id for row in intervals}), 2)
                self.assertTrue(all(row.connection_id is not None for row in intervals))
                self.assertGreaterEqual(state.get_model('learning', 'Classroom').objects.get(pk=room.pk).capacity, 53)
            with connection.cursor() as cursor:
                constraints = connection.introspection.get_constraints(cursor, 'learning_attendanceinterval')
                self.assertTrue(constraints['attendance_one_open_interval']['unique'])
                for table, name in [('learning_whiteboardoperation', 'whiteboard_operation_unique'),
                                    ('learning_classroomchatmessage', 'classroom_chat_retry_unique'),
                                    ('learning_classroominvitation', 'classroom_unique_pending_invite')]:
                    constraints = connection.introspection.get_constraints(cursor, table)
                    self.assertTrue(constraints[name]['unique'])
        finally:
            MigrationExecutor(connection).migrate(latest)

    def test_empty_feature_schema_can_reverse_to_0007_and_reapply_0013(self):
        latest = MigrationExecutor(connection).loader.graph.leaf_nodes('learning')
        try:
            self.migrate('0007_coursecomment_courselike')
            self.assertNotIn('learning_classroom', connection.introspection.table_names())
            MigrationExecutor(connection).migrate(latest)
            tables = connection.introspection.table_names()
            self.assertIn('learning_whiteboard', tables)
            self.assertIn('learning_classroomchatmessage', tables)
        finally:
            MigrationExecutor(connection).migrate(latest)

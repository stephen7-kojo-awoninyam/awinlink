from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class ClassroomConnectionMigrationTests(TransactionTestCase):
    def test_existing_intervals_receive_distinct_connection_ids(self):
        previous = [("learning", "0008_classroom_live_sessions")]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes("learning")
        executor.migrate(previous)
        try:
            old = executor.loader.project_state(previous).apps
            user = get_user_model().objects.create_user(username="migration-host")
            category = old.get_model("learning", "LearningCategory").objects.create(name="Art")
            course = old.get_model("learning", "Course").objects.create(creator_id=user.pk,
                category=category, title="Art", slug="migration-art", description="Art")
            lesson = old.get_model("learning", "Lesson").objects.create(course=course, title="Art", order=1)
            classroom = old.get_model("learning", "Classroom").objects.create(course=course,
                created_by_id=user.pk, title="Art room")
            member = old.get_model("learning", "ClassroomMembership").objects.create(
                classroom=classroom, user_id=user.pk, role="HOST")
            now = timezone.now()
            session = old.get_model("learning", "LiveSession").objects.create(
                classroom=classroom, lesson=lesson, title="Live", status="LIVE", started_at=now)
            participant = old.get_model("learning", "SessionParticipant").objects.create(
                session=session, membership=member, role="HOST", admission_state="ADMITTED", admitted_at=now)
            Interval = old.get_model("learning", "AttendanceInterval")
            for minute in [0, 2]:
                Interval.objects.create(participant=participant, joined_at=now + timedelta(minutes=minute),
                    left_at=now + timedelta(minutes=minute + 1))
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            new = executor.loader.project_state(latest).apps
            ids = list(new.get_model("learning", "AttendanceInterval").objects.values_list("connection_id", flat=True))
            self.assertEqual(len(ids), 2)
            self.assertEqual(len(set(ids)), 2)
            self.assertNotIn(None, ids)
            self.assertEqual(new.get_model("learning", "Classroom").objects.get(pk=classroom.pk).capacity, 50)
        finally:
            MigrationExecutor(connection).migrate(latest)

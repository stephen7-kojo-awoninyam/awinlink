from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, close_old_connections, models, transaction
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone

from . import classroom_services as services
from .models import (
    AdmissionState, AttendanceInterval, Classroom, ClassroomMembership, ClassroomRole,
    Course, Enrollment, LearningCategory, Lesson, LiveSession, SessionAuditEvent, SessionParticipant,
)


class ClassroomFixture:
    def setUp(self):
        User = get_user_model()
        self.creator = User.objects.create_user(username="creator")
        self.host = User.objects.create_user(username="host", role="COACH")
        self.cohost = User.objects.create_user(username="cohost")
        self.learner = User.objects.create_user(username="learner")
        self.other = User.objects.create_user(username="other")
        self.admin = User.objects.create_user(username="admin", role="ADMIN", is_staff=True)
        self.category = LearningCategory.objects.create(name="Art")
        self.course = Course.objects.create(creator=self.creator, category=self.category,
            title="Art", slug="art", description="Art", status="APPROVED")
        self.lesson = Lesson.objects.create(course=self.course, title="Drawing", order=1)
        for user in [self.learner, self.other]:
            Enrollment.objects.create(user=user, course=self.course)
        self.classroom = services.create_classroom(actor=self.creator, course=self.course,
            title="Art room", capacity=10, host=self.host)
        services.assign_classroom_role(actor=self.creator, classroom=self.classroom,
            user=self.cohost, role=ClassroomRole.COHOST)
        self.session = self.schedule()
        services.start_session(actor=self.host, session=self.session)

    def schedule(self, actor=None, classroom=None):
        start = timezone.now() + timedelta(hours=1)
        return services.schedule_session(actor=actor or self.creator, classroom=classroom or self.classroom,
            lesson=self.lesson, title="Drawing", scheduled_start=start, scheduled_end=start + timedelta(hours=1))

    def request(self, user=None, session=None):
        return services.request_admission(actor=user or self.learner, session=session or self.session)

    def admit(self, user=None, actor=None, session=None):
        participant = self.request(user, session)
        return services.admit_participant(actor=actor or self.host, session=session or self.session, participant=participant)

    def join(self, user=None, connection=None):
        return services.join_session(actor=user or self.learner, session=self.session, connection_id=connection or uuid4())


class ClassroomSecurityTests(ClassroomFixture, TestCase):
    def test_unrelated_users_admins_and_learners_cannot_manage(self):
        participant = self.request()
        for actor in [self.learner, self.other, self.admin, AnonymousUser()]:
            operations = [
                lambda: services.create_classroom(actor=actor, course=self.course, title="Attack"),
                lambda: self.schedule(actor=actor),
                lambda: services.start_session(actor=actor, session=self.session),
                lambda: services.end_session(actor=actor, session=self.session),
                lambda: services.cancel_session(actor=actor, session=self.session),
                lambda: services.admit_participant(actor=actor, session=self.session, participant=participant),
                lambda: services.remove_participant(actor=actor, session=self.session, participant=participant),
                lambda: services.assign_classroom_role(actor=actor, classroom=self.classroom, user=actor, role="HOST"),
            ]
            for operation in operations:
                with self.subTest(actor=str(actor), operation=operation), self.assertRaises(PermissionDenied):
                    operation()
        participant.refresh_from_db()
        self.assertEqual(participant.admission_state, AdmissionState.WAITING)

    def test_only_creator_can_create_or_assign_hosts(self):
        for actor in [self.host, self.cohost]:
            with self.assertRaises(PermissionDenied):
                services.create_classroom(actor=actor, course=self.course, title="Attack")
            with self.assertRaises(PermissionDenied):
                services.assign_classroom_role(actor=actor, classroom=self.classroom, user=self.other, role="HOST")
        self.assertTrue(self.classroom.audit_events.filter(event_type="CLASSROOM_CREATED", actor=self.creator).exists())

    def test_cohost_can_moderate_learners_but_not_staff_or_lifecycle(self):
        learner = self.admit(actor=self.cohost)
        self.join()
        services.remove_participant(actor=self.cohost, session=self.session, participant=learner)
        host = self.session.participants.get(membership__user=self.host)
        for operation in [
            lambda: self.schedule(actor=self.cohost),
            lambda: services.start_session(actor=self.cohost, session=self.session),
            lambda: services.end_session(actor=self.cohost, session=self.session),
            lambda: services.cancel_session(actor=self.cohost, session=self.session),
            lambda: services.remove_participant(actor=self.cohost, session=self.session, participant=host),
            lambda: services.admit_participant(actor=self.cohost, session=self.session, participant=host),
        ]:
            with self.assertRaises(PermissionDenied):
                operation()

    def test_assigned_host_is_scoped_to_classroom(self):
        other = services.create_classroom(actor=self.creator, course=self.course, title="Other")
        with self.assertRaises(PermissionDenied):
            self.schedule(actor=self.host, classroom=other)
        self.schedule(actor=self.host)

    def test_inactive_and_stale_user_records_cannot_authorize(self):
        get_user_model().objects.filter(pk=self.host.pk).update(is_active=False)
        self.assertTrue(self.host.is_active)
        with self.assertRaises(PermissionDenied):
            services.end_session(actor=self.host, session=self.session)
        with self.assertRaises(PermissionDenied):
            services.join_session(actor=self.host, session=self.session, connection_id=uuid4())
        self.creator.role = "ADMIN"
        get_user_model().objects.filter(pk=self.creator.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.schedule(actor=self.creator)

    def test_removed_cohost_loses_session_permissions(self):
        participant = self.session.participants.get(membership__user=self.cohost)
        services.remove_participant(actor=self.host, session=self.session, participant=participant)
        target = self.request()
        with self.assertRaises(PermissionDenied):
            services.admit_participant(actor=self.cohost, session=self.session, participant=target)

    def test_waiting_learner_cannot_self_admit_or_join(self):
        participant = self.request()
        with self.assertRaises(PermissionDenied):
            self.join()
        with self.assertRaises(PermissionDenied):
            services.admit_participant(actor=self.learner, session=self.session, participant=participant)
        self.assertFalse(participant.attendance_intervals.exists())

    def test_enrollment_required_at_request_admission_and_join(self):
        with self.assertRaises(PermissionDenied):
            self.request(self.admin)
        participant = self.request()
        Enrollment.objects.filter(user=self.learner, course=self.course).delete()
        with self.assertRaises(PermissionDenied):
            services.admit_participant(actor=self.host, session=self.session, participant=participant)
        Enrollment.objects.create(user=self.learner, course=self.course)
        self.admit()
        interval = self.join()
        Enrollment.objects.filter(user=self.learner, course=self.course).delete()
        with self.assertRaises(PermissionDenied):
            self.join()
        # Loss of access must still allow cleanup of the actor's own connection.
        services.leave_session(actor=self.learner, session=self.session, connection_id=interval.connection_id)

    def test_inactive_membership_blocks_join(self):
        self.admit()
        ClassroomMembership.objects.filter(classroom=self.classroom, user=self.learner).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.join()

    def test_capacity_includes_staff_and_is_reserved_on_admission(self):
        Classroom.objects.filter(pk=self.classroom.pk).update(capacity=4)
        participant = self.admit()
        # Three staff plus one learner fill all four seats.
        self.join()
        self.join(self.host)
        self.assertEqual(services.admit_participant(actor=self.host, session=self.session, participant=participant).pk, participant.pk)
        other = self.request(self.other)
        with self.assertRaises(ValidationError):
            services.admit_participant(actor=self.host, session=self.session, participant=other)
        services.remove_participant(actor=self.host, session=self.session, participant=participant)
        services.admit_participant(actor=self.host, session=self.session, participant=other)
        with self.assertRaises(ValidationError):
            Classroom.objects.filter(pk=self.classroom.pk).update(capacity=3)

    def test_safe_reconnect_idempotency_and_stale_leave(self):
        self.admit()
        first = self.join()
        retry = self.join(connection=first.connection_id)
        self.assertEqual(first.pk, retry.pk)
        self.assertEqual(self.session.audit_events.filter(event_type="JOINED").count(), 1)
        second = self.join()
        first.refresh_from_db()
        self.assertEqual(first.left_at, second.joined_at)
        services.leave_session(actor=self.learner, session=self.session, connection_id=first.connection_id)
        second.refresh_from_db()
        self.assertIsNone(second.left_at)
        with self.assertRaises(ValidationError):
            self.join(connection=first.connection_id)
        self.assertEqual(AttendanceInterval.objects.filter(participant=second.participant, left_at__isnull=True).count(), 1)
        services.leave_session(actor=self.learner, session=self.session, connection_id=second.connection_id)
        events = self.session.audit_events.count()
        services.leave_session(actor=self.learner, session=self.session, connection_id=second.connection_id)
        self.assertEqual(events, self.session.audit_events.count())

    def test_connections_cannot_be_stolen_or_used_to_disconnect_others(self):
        self.admit()
        self.admit(self.other)
        interval = self.join()
        with self.assertRaises(PermissionDenied):
            self.join(self.other, interval.connection_id)
        with self.assertRaises(PermissionDenied):
            services.leave_session(actor=self.other, session=self.session, connection_id=interval.connection_id)
        with self.assertRaises(ValidationError):
            self.join(connection="invalid")
        interval.refresh_from_db()
        self.assertIsNone(interval.left_at)

    def test_remove_closes_attendance_and_requires_explicit_readmission(self):
        participant = self.admit()
        interval = self.join()
        services.remove_participant(actor=self.host, session=self.session, participant=participant)
        interval.refresh_from_db()
        self.assertIsNotNone(interval.left_at)
        for operation in [lambda: self.join(), lambda: self.request()]:
            with self.assertRaises(PermissionDenied):
                operation()
        services.admit_participant(actor=self.host, session=self.session, participant=participant)
        with self.assertRaises(ValidationError):
            self.join(connection=interval.connection_id)
        self.join()
        events = self.session.audit_events.filter(participant=participant).values_list("event_type", flat=True)
        self.assertEqual(list(events), ["REQUESTED", "ADMITTED", "JOINED", "LEFT", "REMOVED", "ADMITTED", "JOINED"])

    def test_end_is_atomic_closes_all_attendance_and_is_idempotent(self):
        self.admit()
        self.join()
        self.join(self.host)
        ended = services.end_session(actor=self.creator, session=self.session)
        self.assertFalse(AttendanceInterval.objects.filter(participant__session=self.session, left_at__isnull=True).exists())
        self.assertTrue(all(at == ended.ended_at for at in AttendanceInterval.objects.filter(
            participant__session=self.session).values_list("left_at", flat=True)))
        services.end_session(actor=self.host, session=self.session)
        self.assertEqual(self.session.audit_events.filter(event_type="ENDED").count(), 1)
        with self.assertRaises(ValidationError):
            self.join()
        with self.assertRaises(ValidationError):
            services.start_session(actor=self.host, session=ended)

    def test_cancel_only_scheduled_and_terminal_operations_fail(self):
        scheduled = self.schedule()
        cancelled = services.cancel_session(actor=self.host, session=scheduled)
        services.cancel_session(actor=self.creator, session=scheduled)
        self.assertEqual(cancelled.audit_events.filter(event_type="CANCELLED").count(), 1)
        for operation in [
            lambda: services.start_session(actor=self.host, session=scheduled),
            lambda: self.request(session=scheduled),
            lambda: services.join_session(actor=self.host, session=scheduled, connection_id=uuid4()),
            lambda: services.cancel_session(actor=self.host, session=self.session),
        ]:
            with self.assertRaises(ValidationError):
                operation()

    def test_cross_session_targets_are_rejected(self):
        other = self.schedule()
        target = self.request(session=other)
        for operation in [services.admit_participant, services.remove_participant]:
            with self.assertRaises(PermissionDenied):
                operation(actor=self.host, session=self.session, participant=target)

    def test_audit_failure_rolls_back_admission_and_reconnect(self):
        participant = self.request()
        with patch("learning.classroom_services._audit", side_effect=RuntimeError("audit failed")):
            with self.assertRaises(RuntimeError):
                services.admit_participant(actor=self.host, session=self.session, participant=participant)
        participant.refresh_from_db()
        self.assertEqual(participant.admission_state, AdmissionState.WAITING)
        self.admit()
        first = self.join()
        with patch("learning.classroom_services._audit", side_effect=RuntimeError("audit failed")):
            with self.assertRaises(RuntimeError):
                self.join()
            with self.assertRaises(RuntimeError):
                services.end_session(actor=self.host, session=self.session)
        first.refresh_from_db()
        self.session.refresh_from_db()
        self.assertIsNone(first.left_at)
        self.assertEqual(self.session.status, LiveSession.Status.LIVE)
        self.assertEqual(first.participant.attendance_intervals.count(), 1)

    def test_schedule_validation_and_rollback(self):
        start = timezone.now() + timedelta(hours=1)
        for end in [start, start - timedelta(hours=1)]:
            with self.assertRaises(ValidationError):
                services.schedule_session(actor=self.host, classroom=self.classroom, lesson=self.lesson,
                    title="Invalid", scheduled_start=start, scheduled_end=end)
        other_course = Course.objects.create(creator=self.creator, category=self.category,
            title="Other", slug="other", description="Other")
        other_lesson = Lesson.objects.create(course=other_course, title="Other", order=1)
        count = LiveSession.objects.count()
        with self.assertRaises(ValidationError):
            services.schedule_session(actor=self.host, classroom=self.classroom, lesson=other_lesson,
                title="Invalid", scheduled_start=start, scheduled_end=start + timedelta(hours=1))
        self.assertEqual(LiveSession.objects.count(), count)

    def test_inactive_classroom_blocks_schedule_request_start_and_join(self):
        self.admit()
        scheduled = self.schedule()
        Classroom.objects.filter(pk=self.classroom.pk).update(is_active=False)
        for operation in [lambda: self.schedule(), lambda: self.request(), lambda: self.join(),
                          lambda: services.start_session(actor=self.host, session=scheduled)]:
            with self.assertRaises(ValidationError):
                operation()
        # Hosts can end disabled classrooms to clean up.
        services.end_session(actor=self.host, session=self.session)

    def test_atomic_host_transfer_updates_scheduled_assignments(self):
        services.end_session(actor=self.creator, session=self.session)
        scheduled = self.schedule()
        services.assign_classroom_role(actor=self.creator, classroom=self.classroom, user=self.other, role="HOST")
        self.assertEqual(scheduled.participants.get(membership__user=self.host).role, ClassroomRole.COHOST)
        self.assertEqual(scheduled.participants.get(membership__user=self.other).role, ClassroomRole.HOST)
        services.start_session(actor=self.other, session=scheduled)
        with self.assertRaises(PermissionDenied):
            services.end_session(actor=self.host, session=scheduled)


class ClassroomBulkValidationTests(ClassroomFixture, TestCase):
    def test_update_bulk_update_and_bulk_create_cannot_cross_classrooms(self):
        target = self.request()
        classroom = services.create_classroom(actor=self.creator, course=self.course, title="Other")
        membership = ClassroomMembership.objects.create(classroom=classroom, user=self.learner)
        for operation in [
            lambda: SessionParticipant.objects.filter(pk=target.pk).update(membership=membership),
            lambda: SessionParticipant.objects.bulk_create([SessionParticipant(session=self.session, membership=membership)]),
        ]:
            with self.assertRaises(ValidationError):
                operation()
        target.membership = membership
        with self.assertRaises(ValidationError):
            SessionParticipant.objects.bulk_update([target], ["membership"])

    def test_admission_and_attendance_validation_cannot_be_bypassed(self):
        target = self.request()
        with self.assertRaises(ValidationError):
            SessionParticipant.objects.filter(pk=target.pk).update(admission_state="ADMITTED")
        with self.assertRaises(ValidationError):
            AttendanceInterval.objects.bulk_create([AttendanceInterval(participant=target)])
        target = self.admit()
        interval = self.join()
        with self.assertRaises(ValidationError):
            SessionParticipant.objects.filter(pk=target.pk).update(admission_state="REMOVED")
        with self.assertRaises(ValidationError):
            LiveSession.objects.filter(pk=self.session.pk).update(status="ENDED", ended_at=timezone.now())
        interval.left_at = interval.joined_at - timedelta(seconds=1)
        with self.assertRaises(ValidationError):
            AttendanceInterval.objects.bulk_update([interval], ["left_at"])

    def test_bulk_batches_roll_back_when_later_rows_fail(self):
        first, second = self.request(), self.request(self.other)
        second.role = "HOST"
        first.admitted_at = timezone.now()
        first.admission_state = "ADMITTED"
        with self.assertRaises(ValidationError):
            SessionParticipant.objects.bulk_update([first, second], ["role", "admission_state", "admitted_at"])
        first.refresh_from_db()
        self.assertEqual(first.admission_state, "WAITING")
        with self.assertRaises(ValidationError):
            Classroom.objects.bulk_create([
                Classroom(course=self.course, created_by=self.creator, title="Valid"),
                Classroom(course=self.course, created_by=self.creator, title="Invalid", capacity=0),
            ])
        self.assertFalse(Classroom.objects.filter(title="Valid").exists())

    def test_bulk_expressions_and_conflict_skipping_fail_closed(self):
        with self.assertRaises(ValidationError):
            Classroom.objects.filter(pk=self.classroom.pk).update(capacity=models.F("capacity") + 1)
        with self.assertRaises(ValidationError):
            Classroom.objects.bulk_create([], ignore_conflicts=True)

    def test_valid_bulk_writes_validate_and_return_counts(self):
        other = services.create_classroom(actor=self.creator, course=self.course, title="Other")
        self.classroom.title = "Updated"
        other.title = "Updated"
        self.assertEqual(Classroom.objects.bulk_update([self.classroom, other], ["title"]), 2)
        self.assertEqual(Classroom.objects.filter(pk__in=[self.classroom.pk, other.pk]).update(title="Again"), 2)
        self.classroom.refresh_from_db()
        self.assertEqual(self.classroom.title, "Again")

    def test_partial_save_validates_persisted_state(self):
        target = self.request()
        target.admitted_at = timezone.now()
        target.admission_state = "ADMITTED"
        with self.assertRaises(ValidationError):
            target.save(update_fields=["admission_state"])
        target.refresh_from_db()
        self.assertEqual(target.admission_state, "WAITING")

    def test_stale_related_objects_cannot_bypass_capacity_or_admission(self):
        self.classroom.capacity = 100
        Classroom.objects.filter(pk=self.classroom.pk).update(capacity=3)
        target = self.request()
        target.session = self.session
        self.session.classroom = self.classroom
        target.admission_state, target.admitted_at = "ADMITTED", timezone.now()
        with self.assertRaises(ValidationError):
            target.save()
        Classroom.objects.filter(pk=self.classroom.pk).update(capacity=10)
        target = self.admit()
        services.remove_participant(actor=self.host, session=self.session, participant=target)
        # The supplied participant still says ADMITTED; validation must reload it.
        with self.assertRaises(ValidationError):
            AttendanceInterval.objects.bulk_create([AttendanceInterval(participant=target)])

    def test_database_constraints_still_reject_invalid_raw_orm_writes(self):
        # Deliberately bypass the validating manager to verify database protection.
        raw = models.QuerySet(model=Classroom, using="default")
        with self.assertRaises(IntegrityError), transaction.atomic():
            raw.filter(pk=self.classroom.pk).update(capacity=0)
        raw = models.QuerySet(model=ClassroomMembership, using="default")
        with self.assertRaises(IntegrityError), transaction.atomic():
            raw.filter(classroom=self.classroom, user=self.creator).update(role="INSTRUCTOR")


class ClassroomConcurrencyTests(ClassroomFixture, TransactionTestCase):
    def race(self, *operations):
        barrier = Barrier(len(operations))

        def run(operation):
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                try:
                    return operation()
                except (ValidationError, PermissionDenied) as error:
                    return error
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(operations)) as pool:
            futures = [pool.submit(run, operation) for operation in operations]
            return [future.result(timeout=30) for future in futures]

    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_admissions_cannot_overbook_last_seat(self):
        Classroom.objects.filter(pk=self.classroom.pk).update(capacity=4)
        first, second = self.request(), self.request(self.other)
        outcomes = self.race(
            lambda: services.admit_participant(actor=self.host, session=self.session, participant=first),
            lambda: services.admit_participant(actor=self.host, session=self.session, participant=second),
        )
        self.assertEqual(sum(isinstance(value, ValidationError) for value in outcomes), 1)
        self.assertEqual(self.session.participants.filter(admission_state="ADMITTED").count(), 4)

    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_reconnects_leave_one_open_interval(self):
        self.admit()
        outcomes = self.race(lambda: self.join(), lambda: self.join())
        self.assertTrue(all(isinstance(value, AttendanceInterval) for value in outcomes))
        intervals = AttendanceInterval.objects.filter(participant__session=self.session)
        self.assertEqual(intervals.count(), 2)
        self.assertEqual(intervals.filter(left_at__isnull=True).count(), 1)

    @skipUnlessDBFeature("has_select_for_update")
    def test_removal_racing_join_never_leaves_attendance_open(self):
        target = self.admit()
        self.race(lambda: self.join(), lambda: services.remove_participant(
            actor=self.host, session=self.session, participant=target))
        target.refresh_from_db()
        self.assertEqual(target.admission_state, "REMOVED")
        self.assertFalse(target.attendance_intervals.filter(left_at__isnull=True).exists())

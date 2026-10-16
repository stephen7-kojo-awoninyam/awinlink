from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from learning.models import (
    AdmissionState, AttendanceInterval, Classroom, ClassroomMembership,
    ClassroomRole, Course, Enrollment, LearningCategory, Lesson, LiveSession,
    SessionAuditEvent, SessionParticipant,
)


class ClassroomModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="classroom-host")
        self.learner = get_user_model().objects.create_user(username="classroom-learner")
        category = LearningCategory.objects.create(name="Arts")
        self.course = Course.objects.create(creator=self.user, category=category,
                                            title="Drawing", slug="drawing", description="Drawing")
        self.lesson = Lesson.objects.create(course=self.course, title="Lines", order=1)
        self.classroom = Classroom.objects.create(course=self.course, title="Drawing group", created_by=self.user)
        self.host = ClassroomMembership.objects.create(classroom=self.classroom, user=self.user, role=ClassroomRole.HOST)
        self.member = ClassroomMembership.objects.create(classroom=self.classroom, user=self.learner)
        Enrollment.objects.create(user=self.learner, course=self.course)
        self.now = timezone.now()
        self.session = LiveSession.objects.create(classroom=self.classroom, lesson=self.lesson,
                                                  title="Live drawing", status=LiveSession.Status.LIVE,
                                                  started_at=self.now)
        self.participant = SessionParticipant.objects.create(session=self.session, membership=self.member,
                                                             admission_state=AdmissionState.ADMITTED,
                                                             admitted_at=self.now)

    def assert_db_rejects(self, operation):
        with self.assertRaises((IntegrityError, ValidationError)), transaction.atomic():
            operation()

    def test_links_defaults_and_roles(self):
        self.assertEqual(self.session.classroom.course, self.lesson.course)
        self.assertEqual(self.member.role, ClassroomRole.LEARNER)
        self.host.role = ClassroomRole.COHOST
        self.host.save()
        cohost = SessionParticipant.objects.create(session=self.session, membership=self.host, role=ClassroomRole.COHOST)
        self.assertEqual(cohost.admission_state, AdmissionState.WAITING)
        self.assertEqual(self.user.role, "ATHLETE")

    def test_membership_uniqueness_and_host_constraints(self):
        with self.assertRaises(ValidationError):
            ClassroomMembership.objects.create(classroom=self.classroom, user=self.user)
        self.assert_db_rejects(lambda: ClassroomMembership.objects.bulk_create([
            ClassroomMembership(classroom=self.classroom, user=self.user)]))
        self.assert_db_rejects(lambda: ClassroomMembership.objects.filter(pk=self.member.pk).update(role="HOST"))
        self.assert_db_rejects(lambda: ClassroomMembership.objects.filter(pk=self.member.pk).update(role="INSTRUCTOR"))
        self.host.is_active = False
        self.host.save()
        self.member.role = ClassroomRole.HOST
        self.member.save()

    def test_lesson_must_match_course_on_save(self):
        other = Course.objects.create(creator=self.user, category=self.course.category,
                                       title="Other", slug="other", description="Other")
        self.session.lesson = Lesson.objects.create(course=other, title="Other", order=1)
        with self.assertRaises(ValidationError):
            self.session.save()

    def test_session_state_and_time_constraints(self):
        invalid_updates = [
            {"status": "INVALID"}, {"started_at": None},
            {"ended_at": self.now}, {"status": "ENDED"},
            {"scheduled_end": self.now},
            {"scheduled_start": self.now, "scheduled_end": self.now},
            {"status": "ENDED", "ended_at": self.now - timedelta(seconds=1)},
        ]
        for update in invalid_updates:
            with self.subTest(update=update):
                self.assert_db_rejects(lambda: LiveSession.objects.filter(pk=self.session.pk).update(**update))
        self.session.status = LiveSession.Status.ENDED
        self.session.ended_at = self.now + timedelta(hours=1)
        self.session.save()

    def test_participant_membership_and_admission_validation(self):
        other = Classroom.objects.create(course=self.course, title="Other", created_by=self.user)
        foreign_member = ClassroomMembership.objects.create(classroom=other, user=self.learner)
        with self.assertRaises(ValidationError):
            SessionParticipant.objects.create(session=self.session, membership=foreign_member)
        self.member.is_active = False
        self.member.save()
        with self.assertRaises(ValidationError):
            self.participant.save()
        for update in [{"role": "INVALID"}, {"admission_state": "INVALID"}, {"admitted_at": None}]:
            self.assert_db_rejects(lambda: SessionParticipant.objects.filter(pk=self.participant.pk).update(**update))
        self.assert_db_rejects(lambda: SessionParticipant.objects.bulk_create([
            SessionParticipant(session=self.session, membership=self.member)]))

    def test_session_has_at_most_one_host(self):
        SessionParticipant.objects.create(session=self.session, membership=self.host, role=ClassroomRole.HOST)
        self.assert_db_rejects(lambda: SessionParticipant.objects.filter(pk=self.participant.pk).update(role="HOST"))

    def test_attendance_reconnects_and_no_overlap(self):
        end = self.now + timedelta(minutes=5)
        interval = AttendanceInterval.objects.create(participant=self.participant, joined_at=self.now)
        with self.assertRaises(ValidationError):
            AttendanceInterval.objects.create(participant=self.participant, joined_at=end)
        self.assert_db_rejects(lambda: AttendanceInterval.objects.bulk_create([
            AttendanceInterval(participant=self.participant, joined_at=end)]))
        self.assert_db_rejects(lambda: AttendanceInterval.objects.filter(pk=interval.pk).update(left_at=self.now - timedelta(seconds=1)))
        interval.left_at = end
        interval.save()
        with self.assertRaises(ValidationError):
            AttendanceInterval.objects.create(participant=self.participant, joined_at=self.now + timedelta(minutes=1), left_at=end)
        AttendanceInterval.objects.create(participant=self.participant, joined_at=end)
        self.assertEqual(self.participant.attendance_intervals.count(), 2)

    def test_attendance_requires_admission_and_session_time_bounds(self):
        with self.assertRaises(ValidationError):
            AttendanceInterval.objects.create(participant=self.participant, joined_at=self.now - timedelta(seconds=1))
        self.participant.admission_state = AdmissionState.REMOVED
        self.participant.save()
        with self.assertRaises(ValidationError):
            AttendanceInterval.objects.create(participant=self.participant)
        self.session.status = LiveSession.Status.ENDED
        self.session.ended_at = self.now + timedelta(minutes=5)
        self.session.save()
        with self.assertRaises(ValidationError):
            AttendanceInterval.objects.create(participant=self.participant, joined_at=self.now,
                                               left_at=self.now + timedelta(minutes=6))

    def test_audit_session_validation_and_actor_deletion(self):
        actor = get_user_model().objects.create_user(username="audit-actor")
        event = SessionAuditEvent.objects.create(session=self.session, participant=self.participant,
                                                 actor=actor, event_type="ADMITTED", metadata={"reason": "Host approved"})
        other = LiveSession.objects.create(classroom=self.classroom, lesson=self.lesson, title="Next")
        with self.assertRaises(ValidationError):
            SessionAuditEvent.objects.create(session=other, participant=self.participant, event_type="JOINED")
        with self.assertRaises(ValidationError):
            SessionAuditEvent.objects.create(session=self.session, event_type="JOINED", metadata=[])
        self.assert_db_rejects(lambda: SessionAuditEvent.objects.filter(pk=event.pk).update(event_type="INVALID"))
        actor.delete()
        event.refresh_from_db()
        self.assertIsNone(event.actor)


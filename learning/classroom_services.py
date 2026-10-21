"""Transactional classroom operations, independent of signaling and transport.

Every operation locks the classroom first, then the session. Capacity counts
admitted participants (including staff), so admission reserves a seat. PostgreSQL
row locks serialize admission and reconnects; SQLite callers must retry lock errors.
Callers supply a fresh UUID for each new connection and reuse it only for retries.
"""

from uuid import UUID
from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .classroom_permissions import (
    require_active_user, require_classroom_management, require_course_creator,
    require_enrollment, require_session_staff,
)
from .models import (
    AdmissionState, AttendanceInterval, Classroom, ClassroomInvitation, ClassroomMembership,
    ClassroomRole, Course, Enrollment, Lesson, LiveSession, SessionAuditEvent, SessionParticipant,
)
from .classroom_notifications import notify_invitation, notify_session_event
from .classroom_events import emit_classroom_control


def _id(value):
    return getattr(value, "pk", value)


def _locked_classroom(classroom):
    return Classroom.objects.select_for_update().get(pk=_id(classroom))


def _locked_session(session):
    classroom_id = LiveSession.objects.values_list("classroom_id", flat=True).get(pk=_id(session))
    classroom = _locked_classroom(classroom_id)
    current = LiveSession.objects.select_for_update().get(pk=_id(session), classroom=classroom)
    return classroom, current


def _available(classroom):
    if not classroom.is_active:
        raise ValidationError("This classroom is inactive.")


def _open(session, *, live=False):
    statuses = {LiveSession.Status.LIVE} if live else {LiveSession.Status.SCHEDULED, LiveSession.Status.LIVE}
    if session.status not in statuses:
        raise ValidationError("This session does not allow that operation.")


def _audit(actor, event_type, *, classroom=None, session=None, participant=None, **metadata):
    return SessionAuditEvent.objects.create(
        classroom=classroom or session.classroom, session=session, actor=actor,
        participant=participant, event_type=event_type, metadata=metadata,
    )


def _participant(session, participant):
    current = SessionParticipant.objects.select_for_update().filter(pk=_id(participant), session=session).first()
    if current is None:
        raise PermissionDenied("The participant does not belong to this session.")
    return current


def _eligible(participant):
    membership = ClassroomMembership.objects.select_related("user").get(pk=participant.membership_id)
    require_active_user(membership.user)
    if not membership.is_active or membership.role != participant.role:
        raise PermissionDenied("The participant's classroom assignment is no longer active.")
    if membership.role == ClassroomRole.LEARNER:
        require_enrollment(membership.user, participant.session.classroom)
    return membership


def _seat(session, participant=None):
    reserved = session.participants.filter(admission_state=AdmissionState.ADMITTED)
    if participant is not None:
        reserved = reserved.exclude(pk=participant.pk)
    if reserved.count() >= session.classroom.capacity:
        raise ValidationError("The classroom has reached capacity.")


def _close(actor, session, participant, at, *, reason):
    for interval in participant.attendance_intervals.filter(left_at__isnull=True).select_for_update():
        interval.left_at = at
        interval.save(update_fields=["left_at"])
        _audit(actor, "LEFT", session=session, participant=participant,
               connection_id=str(interval.connection_id), reason=reason)


@transaction.atomic
def create_classroom(*, actor, course, title, capacity=50, host=None):
    course = Course.objects.select_for_update().get(pk=_id(course))
    actor = require_course_creator(actor, course)
    host = require_active_user(host or actor)
    classroom = Classroom.objects.create(course=course, title=title, capacity=capacity, created_by=actor)
    ClassroomMembership.objects.create(classroom=classroom, user=host, role=ClassroomRole.HOST)
    if host.pk != actor.pk:
        ClassroomMembership.objects.create(classroom=classroom, user=actor, role=ClassroomRole.COHOST)
    _audit(actor, "CLASSROOM_CREATED", classroom=classroom, host_id=host.pk, capacity=capacity)
    return classroom


@transaction.atomic
def assign_classroom_role(*, actor, classroom, user, role):
    """Only the course creator can assign staff; host transfer is atomic."""
    classroom = _locked_classroom(classroom)
    actor = require_course_creator(actor, classroom.course)
    _available(classroom)
    user = require_active_user(user)
    if role not in ClassroomRole.values:
        raise ValidationError({"role": "Unknown classroom role."})
    if classroom.live_sessions.filter(status=LiveSession.Status.LIVE).exists():
        raise ValidationError("Staff assignments cannot change while a session is live.")
    if role == ClassroomRole.LEARNER:
        require_enrollment(user, classroom)
    member = classroom.memberships.filter(user=user).first()
    if member and member.is_active and member.role == ClassroomRole.HOST and role != ClassroomRole.HOST:
        raise ValidationError("Transfer the host role before changing the current host.")
    if member and member.is_active and member.role == role:
        return member
    if role == ClassroomRole.HOST:
        old = classroom.memberships.filter(role=ClassroomRole.HOST, is_active=True).exclude(user=user).first()
        if old:
            old.role = ClassroomRole.COHOST
            old.save(update_fields=["role"])
            for participant in old.session_participations.filter(session__status=LiveSession.Status.SCHEDULED):
                participant.role = old.role
                participant.save(update_fields=["role"])
    if member is None:
        member = ClassroomMembership(classroom=classroom, user=user)
    member.role, member.is_active = role, True
    member.save()
    for session in classroom.live_sessions.filter(status=LiveSession.Status.SCHEDULED):
        participant = session.participants.filter(membership=member).first()
        if participant:
            participant.role = role
            if role != ClassroomRole.LEARNER and participant.admission_state != AdmissionState.ADMITTED:
                _seat(session, participant)
                participant.admission_state = AdmissionState.ADMITTED
                participant.admitted_at = timezone.now()
            participant.save(update_fields=["role", "admission_state", "admitted_at"])
        elif role != ClassroomRole.LEARNER:
            _seat(session)
            SessionParticipant.objects.create(session=session, membership=member, role=role,
                admission_state=AdmissionState.ADMITTED, admitted_at=timezone.now())
        _audit(actor, "ROLE_CHANGED", session=session, user_id=user.pk, role=role)
    _audit(actor, "ROLE_CHANGED", classroom=classroom, user_id=user.pk, role=role)
    return member


@transaction.atomic
def schedule_session(*, actor, classroom, lesson, title, scheduled_start, scheduled_end):
    classroom = _locked_classroom(classroom)
    actor = require_classroom_management(actor, classroom)
    _available(classroom)
    if not scheduled_start or not scheduled_end or timezone.is_naive(scheduled_start) or timezone.is_naive(scheduled_end):
        raise ValidationError("Scheduling requires timezone-aware start and end times.")
    if scheduled_start <= timezone.now() or scheduled_end <= scheduled_start:
        raise ValidationError("Schedule a future start with a later end.")
    session = LiveSession.objects.create(classroom=classroom, lesson=Lesson.objects.get(pk=_id(lesson)),
                                         title=title, scheduled_start=scheduled_start, scheduled_end=scheduled_end)
    now = timezone.now()
    for member in classroom.memberships.filter(is_active=True, role__in=[ClassroomRole.HOST, ClassroomRole.COHOST]):
        require_active_user(member.user)
        _seat(session)
        SessionParticipant.objects.create(session=session, membership=member, role=member.role,
                                          admission_state=AdmissionState.ADMITTED, admitted_at=now)
    _audit(actor, "CREATED", session=session)
    notify_session_event(actor=actor, session=session, event="SCHEDULED")
    return session


@transaction.atomic
def start_session(*, actor, session):
    classroom, session = _locked_session(session)
    actor = require_session_staff(actor, session)
    _available(classroom)
    if session.status == LiveSession.Status.LIVE:
        return session
    if session.status != LiveSession.Status.SCHEDULED:
        raise ValidationError("Only scheduled sessions can start.")
    session.status, session.started_at = LiveSession.Status.LIVE, timezone.now()
    session.save(update_fields=["status", "started_at"])
    _audit(actor, "STARTED", session=session)
    notify_session_event(actor=actor, session=session, event="STARTED")
    return session


@transaction.atomic
def request_admission(*, actor, session):
    classroom, session = _locked_session(session)
    actor = require_enrollment(actor, classroom)
    _available(classroom)
    _open(session)
    membership, _ = ClassroomMembership.objects.get_or_create(classroom=classroom, user=actor)
    if not membership.is_active:
        raise PermissionDenied("Inactive classroom members cannot request admission.")
    participant, created = SessionParticipant.objects.get_or_create(
        session=session, membership=membership, defaults={"role": membership.role})
    if participant.admission_state in {AdmissionState.DENIED, AdmissionState.REMOVED}:
        raise PermissionDenied("Only a host may restore admission.")
    if created:
        _audit(actor, "REQUESTED", session=session, participant=participant)
    return participant


@transaction.atomic
def admit_participant(*, actor, session, participant):
    classroom, session = _locked_session(session)
    actor = require_session_staff(actor, session, allow_cohost=True)
    _available(classroom)
    _open(session)
    participant = _participant(session, participant)
    membership = _eligible(participant)
    # Co-host moderation is restricted to learners, even if staff were removed.
    if actor.pk != classroom.course.creator_id:
        actor_role = classroom.memberships.get(user=actor).role
        if membership.role == ClassroomRole.HOST or (actor_role == ClassroomRole.COHOST and membership.role != ClassroomRole.LEARNER):
            raise PermissionDenied("This staff role cannot manage that participant.")
    if participant.admission_state == AdmissionState.ADMITTED:
        return participant
    _seat(session, participant)
    participant.admission_state, participant.admitted_at = AdmissionState.ADMITTED, timezone.now()
    participant.save(update_fields=["admission_state", "admitted_at"])
    _audit(actor, "ADMITTED", session=session, participant=participant)
    return participant


def _connection_id(value):
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError({"connection_id": "A valid connection UUID is required."})


@transaction.atomic
def join_session(*, actor, session, connection_id):
    actor = require_active_user(actor)
    classroom, session = _locked_session(session)
    _available(classroom)
    _open(session, live=True)
    participant = session.participants.select_for_update().filter(membership__user=actor).first()
    if participant is None or participant.admission_state != AdmissionState.ADMITTED:
        raise PermissionDenied("Host admission is required before joining.")
    _eligible(participant)
    _seat(session, participant)
    connection_id = _connection_id(connection_id)
    previous = AttendanceInterval.objects.filter(connection_id=connection_id).first()
    if previous:
        if previous.participant_id != participant.pk:
            raise PermissionDenied("This connection belongs to another participant.")
        if previous.left_at is not None:
            raise ValidationError("A closed connection cannot be replayed; use a new UUID.")
        return previous
    now = timezone.now()
    _close(actor, session, participant, now, reason="reconnect")
    interval = AttendanceInterval.objects.create(participant=participant, joined_at=now, connection_id=connection_id)
    _audit(actor, "JOINED", session=session, participant=participant, connection_id=str(connection_id))
    emit_classroom_control(session.pk)
    return interval


@transaction.atomic
def leave_session(*, actor, session, connection_id):
    actor = require_active_user(actor)
    _, session = _locked_session(session)
    interval = AttendanceInterval.objects.select_for_update().filter(
        participant__session=session, participant__membership__user=actor,
        connection_id=_connection_id(connection_id),
    ).first()
    if interval is None:
        raise PermissionDenied("This connection does not belong to you in this session.")
    if interval.left_at is None:
        interval.left_at = timezone.now()
        interval.save(update_fields=["left_at"])
        _audit(actor, "LEFT", session=session, participant=interval.participant,
               connection_id=str(interval.connection_id), reason="leave")
        emit_classroom_control(session.pk)
    return interval


@transaction.atomic
def remove_participant(*, actor, session, participant):
    classroom, session = _locked_session(session)
    actor = require_session_staff(actor, session, allow_cohost=True)
    _open(session)
    participant = _participant(session, participant)
    target_role = participant.membership.role
    if participant.membership.user_id == actor.pk:
        raise PermissionDenied("Use leave to disconnect yourself.")
    if actor.pk != classroom.course.creator_id:
        actor_role = classroom.memberships.get(user=actor).role
        if target_role == ClassroomRole.HOST or (actor_role == ClassroomRole.COHOST and target_role != ClassroomRole.LEARNER):
            raise PermissionDenied("This staff role cannot remove that participant.")
    if participant.admission_state == AdmissionState.REMOVED:
        return participant
    _close(actor, session, participant, timezone.now(), reason="removed")
    participant.admission_state = AdmissionState.REMOVED
    participant.save(update_fields=["admission_state"])
    _audit(actor, "REMOVED", session=session, participant=participant)
    emit_classroom_control(session.pk, "removed")
    return participant


@transaction.atomic
def end_session(*, actor, session):
    _, session = _locked_session(session)
    actor = require_session_staff(actor, session)
    if session.status == LiveSession.Status.ENDED:
        return session
    _open(session, live=True)
    now = timezone.now()
    for participant in session.participants.all():
        _close(actor, session, participant, now, reason="session_ended")
    session.status, session.ended_at = LiveSession.Status.ENDED, now
    session.save(update_fields=["status", "ended_at"])
    _audit(actor, "ENDED", session=session)
    notify_session_event(actor=actor, session=session, event="ENDED")
    emit_classroom_control(session.pk, "ended")
    return session


@transaction.atomic
def cancel_session(*, actor, session):
    _, session = _locked_session(session)
    actor = require_session_staff(actor, session)
    if session.status == LiveSession.Status.CANCELLED:
        return session
    if session.status != LiveSession.Status.SCHEDULED:
        raise ValidationError("Only scheduled sessions can be cancelled; end live sessions.")
    session.status = LiveSession.Status.CANCELLED
    session.save(update_fields=["status"])
    _audit(actor, "CANCELLED", session=session)
    notify_session_event(actor=actor, session=session, event="CANCELLED")
    emit_classroom_control(session.pk, "cancelled")
    return session


@transaction.atomic
def invite_classroom_user(*, actor, classroom, recipient, message="", expires_at=None):
    classroom = _locked_classroom(classroom)
    actor = require_classroom_management(actor, classroom)
    _available(classroom)
    if classroom.course.status != "APPROVED":
        raise ValidationError("Only approved courses can invite learners.")
    recipient = require_active_user(recipient)
    if recipient.pk in {actor.pk, classroom.course.creator_id}:
        raise ValidationError("The creator and inviter cannot be invited as learners.")
    member = classroom.memberships.filter(user=recipient).first()
    if member and (not member.is_active or member.role != ClassroomRole.LEARNER):
        raise PermissionDenied("Inactive members and assigned staff cannot be invited as learners.")
    if member and member.is_active:
        raise ValidationError("This user is already a classroom member.")
    now = timezone.now()
    expires_at = expires_at or now + timedelta(days=7)
    if timezone.is_naive(expires_at) or expires_at <= now or expires_at > now + timedelta(days=30):
        raise ValidationError({"expires_at": "Use a timezone-aware future expiry within 30 days."})
    pending = classroom.invitations.select_for_update().filter(recipient=recipient, status="PENDING").first()
    if pending and pending.expires_at > now:
        return pending, False
    if pending:
        pending.status, pending.responded_at = ClassroomInvitation.Status.EXPIRED, now
        pending.save(update_fields=["status", "responded_at"])
        _audit(actor, "INVITATION_EXPIRED", classroom=classroom, invitation_id=pending.pk)
    invitation = ClassroomInvitation.objects.create(classroom=classroom, recipient=recipient,
        invited_by=actor, message=message, expires_at=expires_at)
    _audit(actor, "CLASSROOM_INVITED", classroom=classroom, invitation_id=invitation.pk, recipient_id=recipient.pk)
    notify_invitation(actor=actor, invitation=invitation, event="INVITED")
    return invitation, True


def _locked_invitation(invitation):
    classroom_id = ClassroomInvitation.objects.values_list("classroom_id", flat=True).get(pk=_id(invitation))
    classroom = _locked_classroom(classroom_id)
    return classroom, ClassroomInvitation.objects.select_for_update().get(pk=_id(invitation), classroom=classroom)


def _invitation_recipient(actor, invitation):
    actor = require_active_user(actor)
    if actor.pk != invitation.recipient_id:
        raise PermissionDenied("Only the invited recipient may respond.")
    return actor


def _pending_invitation(invitation):
    if invitation.status != ClassroomInvitation.Status.PENDING:
        raise ValidationError("The invitation has already been completed.")
    if invitation.expires_at <= timezone.now():
        raise ValidationError("The invitation has expired.")


@transaction.atomic
def accept_classroom_invitation(*, actor, invitation):
    classroom, invitation = _locked_invitation(invitation)
    actor = _invitation_recipient(actor, invitation)
    _available(classroom)
    if classroom.course.status != "APPROVED":
        raise ValidationError("The course is not available for enrollment.")
    require_classroom_management(invitation.invited_by, classroom)
    member = classroom.memberships.filter(user=actor).first()
    if member and (not member.is_active or member.role != ClassroomRole.LEARNER):
        raise PermissionDenied("This invitation cannot change an inactive or staff assignment.")
    if invitation.status == ClassroomInvitation.Status.ACCEPTED:
        # A retry must not recreate deleted enrollment or reactivate membership.
        require_enrollment(actor, classroom)
        if member is None:
            raise PermissionDenied("The accepted membership is no longer available.")
        return invitation
    _pending_invitation(invitation)
    Enrollment.objects.get_or_create(user=actor, course=classroom.course)
    ClassroomMembership.objects.get_or_create(classroom=classroom, user=actor,
                                             defaults={"role": ClassroomRole.LEARNER})
    invitation.status, invitation.responded_at = ClassroomInvitation.Status.ACCEPTED, timezone.now()
    invitation.save(update_fields=["status", "responded_at"])
    _audit(actor, "INVITATION_ACCEPTED", classroom=classroom, invitation_id=invitation.pk)
    notify_invitation(actor=actor, invitation=invitation, event="ACCEPTED")
    return invitation


@transaction.atomic
def decline_classroom_invitation(*, actor, invitation):
    classroom, invitation = _locked_invitation(invitation)
    actor = _invitation_recipient(actor, invitation)
    if invitation.status == ClassroomInvitation.Status.DECLINED:
        return invitation
    _pending_invitation(invitation)
    invitation.status, invitation.responded_at = ClassroomInvitation.Status.DECLINED, timezone.now()
    invitation.save(update_fields=["status", "responded_at"])
    _audit(actor, "INVITATION_DECLINED", classroom=classroom, invitation_id=invitation.pk)
    notify_invitation(actor=actor, invitation=invitation, event="DECLINED")
    return invitation


@transaction.atomic
def revoke_classroom_invitation(*, actor, invitation):
    classroom, invitation = _locked_invitation(invitation)
    actor = require_classroom_management(actor, classroom)
    if invitation.status == ClassroomInvitation.Status.REVOKED:
        return invitation
    _pending_invitation(invitation)
    invitation.status, invitation.responded_at = ClassroomInvitation.Status.REVOKED, timezone.now()
    invitation.save(update_fields=["status", "responded_at"])
    _audit(actor, "INVITATION_REVOKED", classroom=classroom, invitation_id=invitation.pk)
    return invitation


@transaction.atomic
def remove_classroom_cohost(*, actor, classroom, user):
    classroom = _locked_classroom(classroom)
    actor = require_course_creator(actor, classroom.course)
    _available(classroom)
    if classroom.live_sessions.filter(status=LiveSession.Status.LIVE).exists():
        raise ValidationError("Staff assignments cannot change while a session is live.")
    member = classroom.memberships.select_for_update().get(user=user)
    if member.role != ClassroomRole.COHOST:
        raise PermissionDenied("Only cohosts may be removed. Transfer the host role first.")
    member.is_active = False
    member.save(update_fields=["is_active"])
    member.session_participations.filter(session__status=LiveSession.Status.SCHEDULED).update(admission_state=AdmissionState.REMOVED)
    _audit(actor, "ROLE_CHANGED", classroom=classroom, user_id=user.pk, role="REMOVED")

"""Classroom capabilities use current database records, never account-role shortcuts."""

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied

from .models import AdmissionState, Classroom, ClassroomMembership, ClassroomRole, Course, Enrollment, LiveSession, SessionParticipant


def require_active_user(user):
    if not getattr(user, "is_authenticated", False) or not getattr(user, "pk", None):
        raise PermissionDenied("An authenticated active account is required.")
    current = get_user_model().objects.filter(pk=user.pk, is_active=True).first()
    if current is None:
        raise PermissionDenied("An authenticated active account is required.")
    return current


def require_course_creator(user, course):
    user = require_active_user(user)
    course = Course.objects.get(pk=course.pk)
    if course.creator_id != user.pk or user.role not in {"ATHLETE", "ORGANIZATION", "SCOUT", "COACH", "ADMIN"}:
        raise PermissionDenied("Only the authorized course creator can create classrooms or assign staff.")
    return user


def require_classroom_management(user, classroom):
    user = require_active_user(user)
    classroom = Classroom.objects.select_related("course").get(pk=classroom.pk)
    if classroom.course.creator_id == user.pk:
        return user
    if not ClassroomMembership.objects.filter(classroom=classroom, user=user,
                                               is_active=True, role=ClassroomRole.HOST).exists():
        raise PermissionDenied("Only the course creator or an assigned active host may manage this classroom.")
    return user


def require_session_staff(user, session, *, allow_cohost=False):
    user = require_active_user(user)
    session = LiveSession.objects.select_related("classroom__course").get(pk=session.pk)
    if session.classroom.course.creator_id == user.pk:
        return user
    roles = [ClassroomRole.HOST, ClassroomRole.COHOST] if allow_cohost else [ClassroomRole.HOST]
    staff = SessionParticipant.objects.filter(
        session=session, membership__user=user, membership__is_active=True,
        membership__role__in=roles, admission_state=AdmissionState.ADMITTED,
    ).select_related("membership").first()
    if staff is None or staff.role != staff.membership.role:
        raise PermissionDenied("An admitted, assigned session host is required.")
    return user


def require_enrollment(user, classroom):
    user = require_active_user(user)
    classroom = Classroom.objects.get(pk=classroom.pk)
    if not Enrollment.objects.filter(user=user, course_id=classroom.course_id).exists():
        raise PermissionDenied("Current course enrollment is required.")
    return user

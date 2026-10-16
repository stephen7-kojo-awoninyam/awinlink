"""Classroom notification routing through Awinlink's central delivery service."""

from django.core.exceptions import PermissionDenied
from django.db.models import Exists, F, OuterRef, Q
from django.utils import timezone

from notifications import services as notification_services

from .classroom_permissions import require_classroom_management
from .models import AdmissionState, ClassroomInvitation, ClassroomMembership, ClassroomRole, Enrollment, LiveSession


def _eligible_memberships(queryset):
    return queryset.filter(is_active=True, user__is_active=True).annotate(
        enrolled=Exists(Enrollment.objects.filter(user_id=OuterRef("user_id"), course_id=OuterRef("classroom__course_id")))
    ).filter(Q(role__in=[ClassroomRole.HOST, ClassroomRole.COHOST]) |
             Q(role=ClassroomRole.LEARNER, enrolled=True, classroom__course__status="APPROVED"))


def notify_session_event(*, actor, session, event):
    members = _eligible_memberships(ClassroomMembership.objects.filter(classroom=session.classroom))
    if event != "SCHEDULED":
        excluded = session.participants.filter(
            Q(admission_state__in=[AdmissionState.DENIED, AdmissionState.REMOVED]) | ~Q(role=F("membership__role")))
        members = members.exclude(pk__in=excluded.values("membership_id"))
    for member in members.select_related("user").order_by("pk"):
        notification_services.create_notification(
            user=member.user, sender=actor, notification_type="CLASSROOM_SESSION",
            message=f'Classroom session "{session.title}" has been {event.lower()}.',
            metadata={"classroom_id": session.classroom_id, "session_id": session.pk, "event": event},
            deduplication_key=f"learning:session:{session.pk}:{event}:user:{member.user_id}",
        )


def notify_invitation(*, actor, invitation, event):
    recipient = invitation.recipient if event == "INVITED" else invitation.invited_by
    message = (f'You have been invited to classroom "{invitation.classroom.title}". Accepting enrolls you in its course; session admission is separate.'
               if event == "INVITED" else f'A classroom invitation for "{invitation.classroom.title}" was {event.lower()}.')
    if recipient.is_active:
        notification_services.create_notification(
            user=recipient, sender=actor, notification_type="CLASSROOM_INVITATION", message=message,
            metadata={"classroom_id": invitation.classroom_id, "invitation_id": invitation.pk, "event": event},
            deduplication_key=f"learning:invite:{invitation.pk}:{event}:user:{recipient.pk}",
        )


def classroom_notification_is_current(notification):
    """Recheck access before asynchronous delivery of classroom notification data."""
    if notification.notification_type not in {"CLASSROOM_INVITATION", "CLASSROOM_SESSION"}:
        return True
    if not notification.user.is_active or not isinstance(notification.metadata, dict):
        return False
    data = notification.metadata
    if notification.notification_type == "CLASSROOM_INVITATION":
        invitation = ClassroomInvitation.objects.filter(pk=data.get("invitation_id"), classroom_id=data.get("classroom_id")).select_related("classroom__course", "invited_by").first()
        if invitation is None:
            return False
        if data.get("event") == "INVITED":
            if invitation.recipient_id != notification.user_id or invitation.status != "PENDING" or invitation.expires_at <= timezone.now():
                return False
            if not invitation.classroom.is_active or invitation.classroom.course.status != "APPROVED":
                return False
            if invitation.classroom.memberships.filter(user_id=notification.user_id, is_active=False).exists():
                return False
        elif invitation.invited_by_id != notification.user_id:
            return False
        try:
            require_classroom_management(invitation.invited_by, invitation.classroom)
        except PermissionDenied:
            return False
        return True
    session = LiveSession.objects.filter(pk=data.get("session_id"), classroom_id=data.get("classroom_id")).first()
    if session is None:
        return False
    event = data.get("event")
    if event not in {"SCHEDULED", "STARTED", "CANCELLED", "ENDED"}:
        return False
    current_status = {"SCHEDULED": "SCHEDULED", "STARTED": "LIVE", "CANCELLED": "CANCELLED", "ENDED": "ENDED"}
    if session.status != current_status[event]:
        return False
    if event in {"SCHEDULED", "STARTED"} and not session.classroom.is_active:
        return False
    members = _eligible_memberships(ClassroomMembership.objects.filter(classroom=session.classroom, user_id=notification.user_id))
    if event != "SCHEDULED":
        excluded = session.participants.filter(
            Q(admission_state__in=[AdmissionState.DENIED, AdmissionState.REMOVED]) | ~Q(role=F("membership__role")))
        members = members.exclude(pk__in=excluded.values("membership_id"))
    return members.exists()

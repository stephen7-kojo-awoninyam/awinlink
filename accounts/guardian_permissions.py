"""Guardian-scoped, auditable grants. Never grants platform or classroom roles."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .age_policy import _adult, _locked
from .age_safety import guardian_of
from .models import GuardianAuditEvent, GuardianContactPermission, GuardianCoursePermission, User


def authorized_guardian(actor, authorization_id):
    authorization, child = _locked(authorization_id)
    actor = _adult(actor)
    if not guardian_of(actor, child) or authorization.guardian_id != actor.pk:
        raise PermissionDenied("A current verified guardian authorization is required.")
    return authorization, child


def restrict_live_access(child_id, *, course_id=None, contact_id=None):
    """Persist termination in the same transaction; emit existing media cleanup controls on commit."""
    from messaging.models import Call
    from messaging.call_lifecycle import finish_call
    from learning.models import AttendanceInterval, SessionParticipant
    from learning.classroom_services import _locked_session, _close
    from learning.classroom_events import emit_classroom_control
    if course_id is None:
        calls = Call.objects.filter(participants__user_id=child_id, status__in=["RINGING", "ACTIVE"])
        if contact_id is not None:
            calls = calls.filter(participants__user_id=contact_id)
        for call_id in calls.values_list("pk", flat=True).distinct():
            call = Call.objects.select_for_update().get(pk=call_id)
            finish_call(call)
    if contact_id is None:
        participants = SessionParticipant.objects.filter(membership__user_id=child_id,
                                                        admission_state__in=["WAITING", "ADMITTED"])
        if course_id is not None:
            participants = participants.filter(session__classroom__course_id=course_id)
        for participant_id, session_id in list(participants.values_list("pk", "session_id")):
            _, session = _locked_session(session_id)
            participant = SessionParticipant.objects.select_for_update().get(pk=participant_id)
            _close(User.objects.get(pk=child_id), session, participant, timezone.now(), reason="guardian_revocation")
            participant.admission_state = "REMOVED"
            participant.save(update_fields=["admission_state"])
            emit_classroom_control(session_id, "removed")
    from messaging.models import ConversationParticipant
    room_ids = ConversationParticipant.objects.filter(user_id=child_id).values("conversation_id")
    affected = set(ConversationParticipant.objects.filter(conversation_id__in=room_ids).values_list("user_id", flat=True)) | {child_id}
    def publish():
        import logging
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        try:
            for user_id in affected:
                async_to_sync(get_channel_layer().group_send)(f"user_{user_id}", {"type": "age_safety_changed"})
        except Exception:
            logging.getLogger(__name__).warning("Unable to publish age-safety control; current DB checks remain enforced.")
    transaction.on_commit(publish)


@transaction.atomic
def change_permission(*, actor, authorization_id, action, data):
    authorization, child = authorized_guardian(actor, authorization_id)
    if action in {"allow_contact", "remove_contact"}:
        username = data.get("username")
        if not isinstance(username, str) or not 1 <= len(username.strip().lstrip("@")) <= 150:
            raise ValidationError("Enter a contact's username.")
        contact = User.objects.filter(username__iexact=username.strip().lstrip("@"), is_active=True).first()
        if contact is None or contact.pk == child.pk:
            raise ValidationError("Choose an active contact other than the child.")
        calls = data.get("allow_calls", False)
        if type(calls) is not bool:
            raise ValidationError("Choose whether calls are allowed.")
        # Terminate existing calls on any permission change; old media must not survive downgrade/regrant.
        restrict_live_access(child.pk, contact_id=contact.pk)
        if action == "remove_contact":
            authorization.contact_permissions.filter(contact=contact).delete()
        else:
            GuardianContactPermission.objects.update_or_create(authorization=authorization, contact=contact,
                                                               defaults={"allow_calls": calls})
    elif action in {"allow_course", "remove_course"}:
        from learning.models import Course
        course_id = data.get("course_id")
        if isinstance(course_id, str) and course_id.isdigit() and len(course_id) <= 18:
            course_id = int(course_id)
        if type(course_id) is not int or course_id <= 0:
            raise ValidationError("Choose a course.")
        from django.db.models import Q
        course = Course.objects.filter(Q(status="APPROVED") | Q(creator=child), pk=course_id).first()
        if course is None:
            raise ValidationError("Choose an approved course or a course created by this child.")
        live = data.get("allow_live", False)
        if type(live) is not bool:
            raise ValidationError("Choose whether live classrooms are allowed.")
        restrict_live_access(child.pk, course_id=course.pk)
        if action == "remove_course":
            authorization.course_permissions.filter(course=course).delete()
        else:
            GuardianCoursePermission.objects.update_or_create(authorization=authorization, course=course,
                                                              defaults={"allow_live": live})
    else:
        raise ValidationError("Choose a valid guardian permission action.")
    GuardianAuditEvent.objects.create(authorization=authorization, actor=actor, action=action.upper())
    return authorization

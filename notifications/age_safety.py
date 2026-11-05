"""Recheck pending notification delivery and reads against current minor permissions."""
from accounts.age_policy import age_access_allowed
from accounts.age_safety import contact_allowed, minor


def notification_allowed(notification):
    user, sender = notification.user, notification.sender
    if not user.is_active or not age_access_allowed(user):
        return False
    if sender is None or sender.pk == user.pk:
        return True
    if not minor(user) and not minor(sender):
        return True
    if notification.notification_type in {"CLASSROOM_INVITATION", "CLASSROOM_SESSION"}:
        from learning.models import Classroom
        from learning.age_permissions import course_allowed
        classroom = Classroom.objects.filter(pk=(notification.metadata or {}).get("classroom_id")).select_related("course").first()
        return bool(classroom and course_allowed(user, classroom.course, live=True))
    if notification.notification_type == "CONNECTION" and sender.age_group == "TEEN":
        from connections.models import Connection
        return Connection.objects.filter(sender=sender, receiver=user, status__in=["PENDING", "ACCEPTED"]).exists()
    if notification.notification_type == "INCOMING_CALL":
        from messaging.models import Call
        from messaging.age_permissions import call_allowed
        calls = Call.objects.filter(conversation_id=notification.conversation_id, status__in=["RINGING", "ACTIVE"])
        return any(call_allowed(call.pk) for call in calls)
    return contact_allowed(user, sender)


def visible_notifications(query):
    from django.db.models import Q
    from accounts.age_safety import cutoff
    sensitive = query.filter(Q(user__date_of_birth__gt=cutoff(18)) | Q(sender__date_of_birth__gt=cutoff(18)))
    return query.exclude(pk__in=[item.pk for item in sensitive.select_related("user", "sender") if not notification_allowed(item)])

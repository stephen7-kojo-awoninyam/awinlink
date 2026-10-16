"""Session-scoped chat; admission is checked for writes and every delivery."""
from uuid import UUID

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .classroom_services import _locked_session
from .classroom_validation import validate_plaintext
from .models import ClassroomChatMessage
from .whiteboard_services import access, group


def representation(message):
    return {"id": message.pk, "client_id": str(message.client_id), "sender_id": message.sender_id,
            "sender_name": (message.sender.get_full_name() or message.sender.username) if message.sender else "Former participant",
            "text": message.text, "created_at": message.created_at.isoformat()}


@transaction.atomic
def history_page(*, actor, session_id, after=0):
    _, session = _locked_session(session_id)
    access(actor, session)
    if type(after) is not int or not 0 <= after <= 9223372036854775807:
        raise ValidationError("Invalid chat cursor.")
    query = session.chat_messages.select_related("sender")
    if after:
        messages = list(query.filter(pk__gt=after).order_by("pk")[:101])
        has_more = len(messages) > 100
        messages = messages[:100]
    else:
        messages = list(reversed(list(query.order_by("-pk")[:100])))
        has_more = False
    return {"results": [representation(message) for message in messages], "has_more": has_more,
            "next_after": messages[-1].pk if messages else after}


def history(*, actor, session_id, after=0):
    return history_page(actor=actor, session_id=session_id, after=after)["results"]


@transaction.atomic
def send(*, actor, session_id, data):
    if not isinstance(data, dict) or set(data) != {"client_id", "text"}:
        raise ValidationError("Invalid chat fields.")
    validate_plaintext(data["text"])
    try:
        client_id = UUID(data["client_id"])
    except (ValueError, TypeError, AttributeError):
        raise ValidationError("Invalid chat ID.")
    _, session = _locked_session(session_id)
    access(actor, session, edit=True)  # Chat needs live admission, not a whiteboard editing grant.
    existing = ClassroomChatMessage.objects.filter(session=session, client_id=client_id).first()
    if existing:
        if existing.sender_id != actor.pk or existing.text != data["text"]:
            raise PermissionDenied("Chat ID already used.")
        return representation(existing)
    message = ClassroomChatMessage.objects.create(session=session, sender=actor, client_id=client_id, text=data["text"])
    def publish():
        import logging
        try:
            layer = get_channel_layer()
            if layer:
                async_to_sync(layer.group_send)(group(session.pk), {"type": "classroom_chat", "message_id": message.pk})
        except Exception:
            logging.getLogger(__name__).exception("Classroom chat broadcast failed; clients recover history")
    transaction.on_commit(publish)
    return representation(message)


@transaction.atomic
def delivery(*, actor, session_id, message_id):
    _, session = _locked_session(session_id)
    access(actor, session)
    return representation(session.chat_messages.select_related("sender").get(pk=message_id))

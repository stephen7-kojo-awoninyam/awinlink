from django.core.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission

from accounts.age_safety import group_allowed, require_contact
from .models import Call, Conversation, Message


def conversation_allowed(conversation_id):
    return group_allowed(Conversation.objects.get(pk=conversation_id).participants.values_list("user_id", flat=True))


def call_allowed(call_id):
    call = Call.objects.filter(pk=call_id).first()
    return bool(call and call.status in {"RINGING", "ACTIVE"} and group_allowed(call.participants.filter(status__in=["JOINED", "RINGING", "INVITED"]).values_list("user_id", flat=True), calls=True))


def visible_conversations(query):
    # Apply before pagination/counts, including historical rooms and participant previews.
    from accounts.age_safety import cutoff
    sensitive = query.filter(participants__user__date_of_birth__gt=cutoff(18)).distinct()
    return query.exclude(pk__in=[item.pk for item in sensitive.prefetch_related("participants__user")
                                if not group_allowed([member.user_id for member in item.participants.all()])])


class AgeSafeMessagingPermission(BasePermission):
    message = "This interaction requires age-safety approval."

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        args = view.kwargs
        # Leaving/rejecting must remain possible when another participant loses access.
        if view.__class__.__name__ in {"EndCallAPIView", "RejectCallAPIView", "RemoveGroupMemberAPIView"}:
            return True
        if "call_id" in args:
            call = Call.objects.filter(pk=args["call_id"]).first()
            if call is None or call.status not in {"RINGING", "ACTIVE"}:
                return True
            return call_allowed(args["call_id"])
        conversation_id = args.get("conversation_id")
        if "message_id" in args:
            conversation_id = Message.objects.filter(pk=args["message_id"]).values_list("conversation_id", flat=True).first()
        if conversation_id and Conversation.objects.filter(pk=conversation_id).exists():
            if not conversation_allowed(conversation_id):
                return False
            if view.__class__.__name__ == "StartCallAPIView":
                require_contact(request.user, Conversation.objects.get(pk=conversation_id).participants.values_list("user_id", flat=True), calls=True)
        return True

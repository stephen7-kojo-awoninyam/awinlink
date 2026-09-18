from django.db.models import Q
from messaging.models import Message


def unread_messages(request):

    if not request.user.is_authenticated:

        return {
            "unread_message_count": 0
        }

    count = Message.objects.filter(
        is_read=False
    ).filter(
        ~Q(sender=request.user)
    ).filter(
        conversation__participants__user=request.user
    ).distinct().count()

    return {
        "unread_message_count": count
    }
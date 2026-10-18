from django.db.models import F, Q
from messaging.models import Message


def unread_messages(request):

    if not request.user.is_authenticated:

        return {
            "unread_message_count": 0
        }

    count = Message.objects.filter(
        Q(conversation__participants__last_read_at__isnull=True) |
        Q(created_at__gt=F('conversation__participants__last_read_at')),
        conversation__participants__user=request.user,
    ).exclude(sender=request.user).distinct().count()

    return {
        "unread_message_count": count
    }
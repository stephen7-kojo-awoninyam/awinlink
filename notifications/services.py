from .models import Notification


def create_notification(
    user,
    sender=None,
    notification_type="SYSTEM",
    message="",
    post=None,
    opportunity=None,
    conversation=None,
    metadata=None,
    deduplication_key=None,
):
    """
    Central notification creation service.
    """

    # Don't notify yourself
    if sender and user == sender:
        return None

    values = dict(sender=sender, notification_type=notification_type, message=message,
                  post=post, opportunity=opportunity, conversation=conversation, metadata=metadata or {})
    if deduplication_key is not None:
        notification, _ = Notification.objects.get_or_create(
            user=user, deduplication_key=deduplication_key, defaults=values)
        return notification
    return Notification.objects.create(user=user, **values)

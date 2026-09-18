from .models import Notification


def create_notification(
    user,
    sender=None,
    notification_type="SYSTEM",
    message="",
    post=None,
    opportunity=None,
    conversation=None,
):
    """
    Central notification creation service.
    """

    # Don't notify yourself
    if sender and user == sender:
        return None

    return Notification.objects.create(
        user=user,
        sender=sender,
        notification_type=notification_type,
        message=message,
        post=post,
        opportunity=opportunity,
        conversation=conversation,
    )
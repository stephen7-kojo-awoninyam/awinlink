import logging

from asgiref.sync import async_to_sync
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from channels.layers import get_channel_layer

from .models import Notification


logger = logging.getLogger(__name__)


@receiver(post_save, sender=Notification)
def schedule_notification_delivery(sender, instance, created, **kwargs):
    if created:
        transaction.on_commit(
            lambda notification_id=instance.pk: publish_notification(notification_id)
        )


def publish_notification(notification_id):
    try:
        notification = Notification.objects.select_related("user").get(
            pk=notification_id,
        )
        from learning.classroom_notifications import classroom_notification_is_current
        if not classroom_notification_is_current(notification):
            return
        from marketplace.services import booking_notification_is_current
        if not booking_notification_is_current(notification):
            return
        from .push import (
            notification_payload,
            send_expo_call_push,
            send_expo_classroom_push,
            send_push_notification,
        )

        payload = notification_payload(notification)
        send_push_notification(notification)
        send_expo_call_push(notification)
        send_expo_classroom_push(notification)

        channel_layer = get_channel_layer()
        if channel_layer is not None:
            async_to_sync(channel_layer.group_send)(
                f"user_{notification.user_id}",
                {
                    "type": "notification_created",
                    "notification": payload,
                },
            )
    except Exception:
        logger.exception(
            "Unable to deliver notification %s.",
            notification_id,
        )

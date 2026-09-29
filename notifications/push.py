import json
import logging

from django.conf import settings
from django.urls import reverse

from .models import Notification, PushSubscription


logger = logging.getLogger(__name__)


def notification_payload(notification):
    return {
        "id": notification.pk,
        "title": notification.get_notification_type_display(),
        "body": notification.message[:180],
        "url": reverse(
            "notification_detail",
            args=[notification.pk],
        ),
        "notification_type": notification.notification_type,
        "tag": f"awinlink-notification-{notification.pk}",
    }


def send_push_notification(notification):
    if not settings.WEB_PUSH_PUBLIC_KEY or not settings.WEB_PUSH_PRIVATE_KEY:
        return

    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        logger.exception("Web Push is configured but pywebpush is not installed.")
        return

    payload = json.dumps(notification_payload(notification))
    subscriptions = PushSubscription.objects.filter(user=notification.user)

    for subscription in subscriptions.iterator():
        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": subscription.keys,
                },
                data=payload,
                vapid_private_key=settings.WEB_PUSH_PRIVATE_KEY,
                vapid_claims={"sub": settings.WEB_PUSH_SUBJECT},
            )
        except WebPushException as error:
            response = getattr(error, "response", None)
            if getattr(response, "status_code", None) in (404, 410):
                subscription.delete()
                continue
            logger.warning(
                "Web Push delivery failed for subscription %s: %s",
                subscription.pk,
                error,
            )
        except Exception:
            logger.exception(
                "Unexpected Web Push failure for subscription %s.",
                subscription.pk,
            )
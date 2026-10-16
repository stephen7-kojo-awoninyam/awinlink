import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.urls import reverse

from .models import MobilePushToken, Notification, PushSubscription


logger = logging.getLogger(__name__)
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


def notification_payload(notification):
    payload = {
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
    if notification.notification_type in {"CLASSROOM_INVITATION", "CLASSROOM_SESSION"}:
        payload["data"] = classroom_push_data(notification)
    return payload


def classroom_push_data(notification):
    """Allowlisted routing data, without private messages, identities or tokens."""
    metadata = notification.metadata if isinstance(notification.metadata, dict) else {}
    data = {"type": notification.notification_type.lower(), "notification_id": notification.pk}
    for key in ["classroom_id", "session_id", "invitation_id", "event"]:
        if key in metadata:
            data[key] = metadata[key]
    return data


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


def send_expo_call_push(notification):
    """Deliver an incoming-call alert to registered native Android/iOS devices."""
    if notification.notification_type != "INCOMING_CALL" or not notification.conversation_id:
        return

    from messaging.models import Call, CallParticipant

    call = (
        Call.objects.filter(
            conversation_id=notification.conversation_id,
            initiated_by_id=notification.sender_id,
            status="RINGING",
        )
        .order_by("-started_at")
        .first()
    )
    if not call or not CallParticipant.objects.filter(
        call=call, user_id=notification.user_id, status="RINGING"
    ).exists():
        return

    tokens = list(
        MobilePushToken.objects.filter(user_id=notification.user_id).values_list(
            "token", "platform"
        )
    )
    if not tokens:
        return

    caller_name = (
        notification.sender.get_full_name() or notification.sender.username
        if notification.sender_id
        else "Awinlink user"
    )
    call_label = "video" if call.call_type == "VIDEO" else "audio"
    data = {
        "type": "incoming_call",
        "call_id": call.pk,
        "conversation_id": call.conversation_id,
        "call_type": call.call_type,
        "caller_name": caller_name,
    }
    messages = [
        {
            "to": token,
            "title": f"Incoming {call_label} call",
            "body": f"{caller_name} is calling you.",
            "data": data,
            "sound": "default",
            "priority": "high",
            "ttl": 30,
            "channelId": "incoming-calls",
            "categoryId": "incoming-call",
            "collapseId": f"awinlink-call-{call.pk}",
        }
        for token, _platform in tokens
    ]
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    push_access_token = getattr(settings, "EXPO_PUSH_ACCESS_TOKEN", "").strip()
    if push_access_token:
        headers["Authorization"] = f"Bearer {push_access_token}"

    for offset in range(0, len(messages), 100):
        batch = messages[offset : offset + 100]
        try:
            request = Request(
                EXPO_PUSH_URL,
                data=json.dumps(batch).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urlopen(request, timeout=5) as response:
                result = json.loads(response.read().decode("utf-8"))
            tickets = result.get("data", [])
            for index, ticket in enumerate(tickets[: len(batch)]):
                if (
                    ticket.get("status") == "error"
                    and ticket.get("details", {}).get("error") == "DeviceNotRegistered"
                ):
                    MobilePushToken.objects.filter(token=batch[index]["to"]).delete()
        except (HTTPError, URLError, TimeoutError, ValueError, OSError, AttributeError):
            logger.exception(
                "Unable to send Expo call push for call %s to user %s.",
                call.pk,
                notification.user_id,
            )


def send_expo_classroom_push(notification):
    """Use the registered native devices and existing Expo transport for classrooms."""
    if notification.notification_type not in {"CLASSROOM_INVITATION", "CLASSROOM_SESSION"}:
        return
    from learning.classroom_notifications import classroom_notification_is_current
    if not classroom_notification_is_current(notification):
        return
    tokens = list(MobilePushToken.objects.filter(user_id=notification.user_id).values_list("token", flat=True))
    messages = [{"to": token, "title": notification.get_notification_type_display(),
                 "body": notification.message[:180], "data": classroom_push_data(notification),
                 "sound": "default", "ttl": 3600, "collapseId": f"awinlink-notification-{notification.pk}"}
                for token in tokens]
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    push_access_token = getattr(settings, "EXPO_PUSH_ACCESS_TOKEN", "").strip()
    if push_access_token:
        headers["Authorization"] = f"Bearer {push_access_token}"
    for offset in range(0, len(messages), 100):
        batch = messages[offset:offset + 100]
        try:
            request = Request(EXPO_PUSH_URL, data=json.dumps(batch).encode("utf-8"), headers=headers, method="POST")
            with urlopen(request, timeout=5) as response:
                result = json.loads(response.read().decode("utf-8"))
            for index, ticket in enumerate(result.get("data", [])[:len(batch)]):
                if ticket.get("status") == "error" and ticket.get("details", {}).get("error") == "DeviceNotRegistered":
                    MobilePushToken.objects.filter(token=batch[index]["to"]).delete()
        except (HTTPError, URLError, TimeoutError, ValueError, OSError, AttributeError):
            logger.exception("Unable to send Expo classroom push for notification %s.", notification.pk)

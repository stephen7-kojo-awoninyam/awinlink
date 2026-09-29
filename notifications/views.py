import json

from django.shortcuts import (
    render,
    get_object_or_404,
    redirect
)

# create your views here.

from django.conf import settings
from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST

from .models import Notification, PushSubscription


# ==========================================
# NOTIFICATION LIST
# ==========================================

@login_required
def notification_list(request):

    notifications = Notification.objects.filter(
        user=request.user
    ).select_related(
        "sender",
        "post",
        "opportunity",
        "conversation"
    )

    return render(
        request,
        "notifications/list.html",
        {
            "notifications": notifications
        }
    )

@login_required
def notification_detail(
    request,
    notification_id
):

    notification = get_object_or_404(
        Notification,
        id=notification_id,
        user=request.user
    )

    notification.is_read = True

    notification.save(
        update_fields=["is_read"]
    )

    # MESSAGE
    if (
        notification.notification_type == "MESSAGE"
        and notification.conversation
    ):

        return redirect(
            "messaging:conversation",
            conversation_id=notification.conversation.id
        )

    if (
        notification.notification_type in ["INCOMING_CALL", "MISSED_CALL"]
        and notification.conversation
    ):
        return redirect(
            "messaging:conversation",
            conversation_id=notification.conversation.id,
        )

    # POST NOTIFICATIONS
    if (
        notification.notification_type in [
            "LIKE",
            "COMMENT",
            "SHARE"
        ]
        and notification.post
    ):

        return redirect(
            "home_feed"
        )

    # Everything else
    return redirect(
        "notification_list"
    )


# ==========================================
# MARK AS READ
# ==========================================

@login_required
@require_POST
def mark_all_notifications_read(request):
    Notification.objects.filter(
        user=request.user,
        is_read=False,
    ).update(is_read=True)
    return redirect("notification_list")


@login_required
@require_POST
def mark_notification_read(
    request,
    notification_id
):

    notification = get_object_or_404(
        Notification,
        id=notification_id,
        user=request.user
    )

    notification.is_read = True

    notification.save(
        update_fields=["is_read"]
    )

    return redirect(
        "notification_list"
    )


@login_required
@ensure_csrf_cookie
def push_config(request):
    return JsonResponse({
        "public_key": settings.WEB_PUSH_PUBLIC_KEY,
        "configured": bool(
            settings.WEB_PUSH_PUBLIC_KEY
            and settings.WEB_PUSH_PRIVATE_KEY
        ),
    })


@login_required
@require_POST
def manage_push_subscription(request):
    try:
        data = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"detail": "Invalid JSON."}, status=400)

    endpoint = data.get("endpoint") if isinstance(data, dict) else None
    if not isinstance(endpoint, str) or not endpoint.startswith("https://"):
        return JsonResponse(
            {"detail": "A valid push endpoint is required."},
            status=400,
        )

    if data.get("action") == "unsubscribe":
        PushSubscription.objects.filter(
            user=request.user,
            endpoint=endpoint,
        ).delete()
        return JsonResponse({"subscribed": False})

    keys = data.get("keys")
    if not isinstance(keys, dict) or not all(
        isinstance(keys.get(key), str) and keys[key]
        for key in ("p256dh", "auth")
    ):
        return JsonResponse(
            {"detail": "Push encryption keys are required."},
            status=400,
        )

    existing_subscription = PushSubscription.objects.filter(
        endpoint=endpoint,
    ).first()
    if (
        existing_subscription
        and existing_subscription.user_id != request.user.id
    ):
        return JsonResponse(
            {"detail": "This device subscription belongs to another account."},
            status=409,
        )

    PushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            "user": request.user,
            "keys": {
                "p256dh": keys["p256dh"],
                "auth": keys["auth"],
            },
        },
    )
    return JsonResponse({"subscribed": True}, status=201)


def service_worker(request):
    worker_path = settings.BASE_DIR / "static" / "js" / "service-worker.js"
    response = HttpResponse(
        worker_path.read_text(encoding="utf-8"),
        content_type="application/javascript; charset=utf-8",
    )
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response
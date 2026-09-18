from django.shortcuts import (
    render,
    get_object_or_404,
    redirect
)

# create your views here.

from django.contrib.auth.decorators import login_required

from .models import Notification


# ==========================================
# NOTIFICATION LIST
# ==========================================

@login_required
def notification_list(request):

    # Mark all notifications as read when
    # the user opens the notifications page.
    Notification.objects.filter(
        user=request.user,
        is_read=False
    ).update(
        is_read=True
    )

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
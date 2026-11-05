from .models import Notification



def notifications(request):

    if request.user.is_authenticated:

        notifications = Notification.objects.filter(
            user=request.user
        ).order_by(
            "-created_at"
        )


        from .age_safety import visible_notifications
        notifications = visible_notifications(notifications)
        unread_count = notifications.filter(
            is_read=False
        ).count()


        return {

            "user_notifications": notifications[:5],

            "unread_notifications": unread_count

        }


    return {

        "user_notifications": [],

        "unread_notifications": 0

    }

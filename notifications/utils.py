from .models import Notification



def create_notification(
        user,
        message,
        notification_type="SYSTEM"
):

    Notification.objects.create(

        user=user,

        message=message,

        notification_type=notification_type

    )
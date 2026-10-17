from django.db import transaction
from django.utils import timezone
from .models import Connection
from notifications.models import Notification


class ConnectionResponseError(Exception):
    def __init__(self, detail, status_code):
        self.detail = detail
        self.status_code = status_code


@transaction.atomic
def respond_to_connection(connection_id, user, new_status):
    if new_status not in ("ACCEPTED", "REJECTED"):
        raise ConnectionResponseError("Status must be ACCEPTED or REJECTED.", 400)
    connection = Connection.objects.select_for_update().filter(pk=connection_id).first()
    if connection is None:
        raise ConnectionResponseError("Connection request not found.", 404)
    if connection.receiver_id != user.pk:
        raise ConnectionResponseError("Only the receiver can respond to this connection request.", 403)
    if connection.status == new_status:
        return connection
    if connection.status != "PENDING":
        raise ConnectionResponseError("This connection request has already been processed.", 409)
    # Conditional update also prevents duplicate notifications on concurrent retries.
    changed = Connection.objects.filter(pk=connection.pk, status="PENDING").update(
        status=new_status, updated_at=timezone.now()
    )
    connection.refresh_from_db()
    if not changed:
        if connection.status != new_status:
            raise ConnectionResponseError("This connection request has already been processed.", 409)
        return connection
    if new_status == "ACCEPTED":
        Notification.objects.create(
            user_id=connection.sender_id, sender=user, notification_type="CONNECTION",
            message=f"{user.get_full_name() or user.username} accepted your connection request.",
        )
    return connection

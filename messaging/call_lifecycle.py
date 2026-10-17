"""Terminal call transitions. Callers hold the call row lock until commit."""
import logging
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.utils import timezone
from notifications.models import Notification
from .models import CallParticipant

logger = logging.getLogger(__name__)


def publish_call_ended(call, ended_by=None):
    event = {'type': 'call_ended', 'call_id': call.pk, 'status': call.status,
             'ended_by': ended_by, 'ended_by_username': None}
    users = list(call.participants.values_list('user_id', flat=True))

    def publish():
        layer = get_channel_layer()
        for group in [f'call_{call.pk}', *(f'user_{user}' for user in users)]:
            try:
                async_to_sync(layer.group_send)(group, event)
            except Exception:
                # A signaling outage must not roll back cancellation or prevent redial.
                logger.exception('Unable to publish call end for call %s.', call.pk)
    transaction.on_commit(publish)


def finish_call(call, ended_by=None):
    if call.status not in ('RINGING', 'ACTIVE'):
        return
    now = timezone.now()
    call.status = 'ENDED'
    call.ended_at = now
    call.duration = max(0, int((now - call.answered_at).total_seconds())) if call.answered_at else 0
    call.save(update_fields=['status', 'ended_at', 'duration'])
    CallParticipant.objects.filter(call=call, status__in=['JOINED', 'RINGING', 'INVITED']).update(status='LEFT', left_at=now)
    Notification.objects.filter(conversation_id=call.conversation_id, sender_id=call.initiated_by_id,
                                notification_type='INCOMING_CALL', is_read=False).update(is_read=True)
    publish_call_ended(call, ended_by)

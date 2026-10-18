"""Publish committed messages from both web and REST send paths."""
import logging
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Message, ConversationParticipant

logger = logging.getLogger(__name__)


def mark_read(user, conversation_id, at=None):
    from django.db.models import Q
    from django.utils import timezone
    at = at or timezone.now()
    ConversationParticipant.objects.filter(user=user, conversation_id=conversation_id).filter(
        Q(last_read_at__isnull=True) | Q(last_read_at__lt=at)
    ).update(last_read_at=at)
    def committed():
        try:
            async_to_sync(get_channel_layer().group_send)(f'user_{user.pk}', {
                'type': 'messaging_event', 'data': {
                    'type': 'messages_read', 'conversation_id': conversation_id,
                },
            })
        except Exception:
            logger.exception('Unable to publish read update')
    transaction.on_commit(committed)


def can_access(user, conversation_id):
    from accounts.safety import blocked_user_ids
    return (user.is_active and
            ConversationParticipant.objects.filter(conversation_id=conversation_id, user=user, user__is_active=True).exists() and
            not ConversationParticipant.objects.filter(
                conversation_id=conversation_id, user_id__in=blocked_user_ids(user)).exists())


def publish(conversation_id, data):
    layer = get_channel_layer()
    for participant in ConversationParticipant.objects.filter(conversation_id=conversation_id).select_related('user'):
        if can_access(participant.user, conversation_id):
            async_to_sync(layer.group_send)(f'user_{participant.user_id}', {
                'type': 'messaging_event', 'data': data,
            })


@receiver(post_save, sender=Message)
def message_saved(sender, instance, created, **kwargs):
    if not created:
        return
    message_id = instance.pk

    def committed():
        from .serializers import MessageSerializer
        try:
            message = Message.objects.select_related('sender', 'reply_to__sender').get(pk=message_id)
            publish(message.conversation_id, {
                'type': 'message_created', 'conversation_id': message.conversation_id,
                'message': MessageSerializer(message).data,
            })
        except Exception:
            # Delivery failure must not turn a persisted send into a retry/duplicate.
            logger.exception('Unable to publish message %s', message_id)
    transaction.on_commit(committed)

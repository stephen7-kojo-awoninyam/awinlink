from django.db.models.signals import pre_save
from django.dispatch import receiver

from connections.models import Connection, Follow
from feed.models import Comment, PostLike
from messaging.models import Call, Message, ConversationParticipant
from .safety import require_unblocked


@receiver(pre_save, sender=Message)
@receiver(pre_save, sender=Call)
def check_conversation_interaction(sender, instance, **kwargs):
    if not instance._state.adding:
        return
    actor = instance.sender if sender is Message else instance.initiated_by
    require_unblocked(actor, instance.conversation.participants.values_list('user_id', flat=True))


@receiver(pre_save, sender=Connection)
def check_connection(sender, instance, **kwargs):
    require_unblocked(instance.sender, [instance.receiver_id])


@receiver(pre_save, sender=Follow)
def check_follow(sender, instance, **kwargs):
    require_unblocked(instance.follower, [instance.following_id])


@receiver(pre_save, sender=Comment)
@receiver(pre_save, sender=PostLike)
def check_post_interaction(sender, instance, **kwargs):
    require_unblocked(instance.user, [instance.post.author_id])


@receiver(pre_save, sender=ConversationParticipant)
def check_conversation_membership(sender, instance, **kwargs):
    if instance._state.adding:
        require_unblocked(instance.user, instance.conversation.participants.values_list('user_id', flat=True))

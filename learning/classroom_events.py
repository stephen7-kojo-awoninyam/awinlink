"""Post-commit controls across the existing Redis/InMemory Channels layer."""

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction


logger = logging.getLogger(__name__)


def session_group(session_id):
    return f"learning.session.{int(session_id)}"


def participant_group(session_id, participant_id):
    return f"learning.session.{int(session_id)}.participant.{int(participant_id)}"


def emit_classroom_control(session_id, reason="presence"):
    def publish():
        try:
            layer = get_channel_layer()
            if layer is not None:
                async_to_sync(layer.group_send)(session_group(session_id), {
                    "type": "classroom_control", "session_id": int(session_id), "reason": reason,
                })
        except Exception:
            # State is already committed. Socket watchdogs independently recheck
            # access; a Redis outage must not undo removal or session ending.
            logger.exception("Unable to publish classroom control for session %s.", session_id)
    transaction.on_commit(publish)

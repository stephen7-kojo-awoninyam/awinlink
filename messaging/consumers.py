import json
import logging

from django.utils import timezone
from django.db import transaction
from redis.exceptions import RedisError

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from .models import Call, CallParticipant
from .call_lifecycle import finish_call
from .socket_security import SecureSocketMixin


logger = logging.getLogger(__name__)


class CallConsumer(SecureSocketMixin, AsyncWebsocketConsumer):

    async def delivery_allowed(self):
        return await self.check_participant()

    async def connect(self):

        self.call_id = self.scope["url_route"]["kwargs"]["call_id"]
        self.user = self.scope["user"]

        # ---------------------------------------------------------
        # AUTHENTICATION
        # ---------------------------------------------------------

        if not await self.ensure_credentials():
            await self.close(code=4001)
            return

        # ---------------------------------------------------------
        # CHECK CALL PARTICIPATION
        # ---------------------------------------------------------

        is_participant = await self.check_participant()

        if not is_participant:
            await self.close(code=4003)
            return

        # ---------------------------------------------------------
        # CALL ROOM
        # ---------------------------------------------------------

        self.room_group_name = f"call_{self.call_id}"

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()
        self.start_security_watchdog()

        # ---------------------------------------------------------
        # CONFIRM CONNECTION
        # ---------------------------------------------------------

        await self.send(
            text_data=json.dumps({
                "type": "connection",
                "reauthentication": True,
                "message": "Connected to call signaling server.",
                "call_id": self.call_id,
                "user_id": self.user.id,
            })
        )

        # ---------------------------------------------------------
        # TELL OTHER PARTICIPANTS THAT THIS USER JOINED
        # ---------------------------------------------------------

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "participant_joined",
                "user_id": self.user.id,
                "username": self.user.username,
                "sender_channel": self.channel_name,
            }
        )

    async def disconnect(self, close_code):

        self.stop_security_watchdog()

        if hasattr(self, "room_group_name"):

            # -----------------------------------------------------
            # UPDATE DATABASE
            # -----------------------------------------------------

            await self.mark_participant_left()

            # -----------------------------------------------------
            # NOTIFY OTHER PARTICIPANTS
            # -----------------------------------------------------

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "participant_left",
                    "user_id": self.user.id,
                    "sender_channel": self.channel_name,
                }
            )

            # -----------------------------------------------------
            # REMOVE FROM CALL ROOM
            # -----------------------------------------------------

            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive(self, text_data=None, bytes_data=None):

        if not await self.bounded_frame(text_data, bytes_data) or not await self.ensure_credentials():
            return

        if not await self.check_participant():
            await self.close(code=4003)
            return

        try:
            data = json.loads(text_data)

        except (json.JSONDecodeError, TypeError, RecursionError):

            await self.send(
                text_data=json.dumps({
                    "type": "error",
                    "message": "Invalid JSON."
                })
            )

            return

        if not isinstance(data, dict):
            await self.send(text_data=json.dumps({
                "type": "error", "message": "Signaling messages must be JSON objects."
            }))
            return

        if await self.reauthenticate(data):
            return


        # ---------------------------------------------------------
        # ADD SENDER INFORMATION
        # ---------------------------------------------------------

        # Normalize older web payloads while retaining aliases for older clients.
        if data.get("type") == "ice-candidate":
            data["type"] = "ice_candidate"
        if data.get("type") in ("offer", "answer"):
            description = data.get("description") or data.get(data["type"])
            if description is not None:
                data["description"] = description
                data[data["type"]] = description
        target = data.get("to_user_id", data.get("target_id"))
        if target is not None:
            try:
                target = int(target)
            except (TypeError, ValueError):
                await self.send(text_data=json.dumps({"type": "error", "message": "Invalid signal recipient."}))
                return
            data["to_user_id"] = target
            data["target_id"] = target
        data["sender_id"] = self.user.id

        # ---------------------------------------------------------
        # RELAY SIGNALING MESSAGE
        # ---------------------------------------------------------

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "call_signal",
                "data": data,
                "sender_channel": self.channel_name,
            }
        )

    async def call_signal(self, event):

        # Do not send the signaling message
        # back to the browser that sent it.

        if event.get("sender_channel") == self.channel_name:
            return

        target = event["data"].get("to_user_id", event["data"].get("target_id"))
        if target is not None and int(target) != self.user.id:
            return
        await self.send(
            text_data=json.dumps(
                event["data"]
            )
        )

    async def participant_joined(self, event):

        if event.get("sender_channel") == self.channel_name:
            return

        await self.send(
            text_data=json.dumps({
                "type": "participant_joined",
                "user_id": event["user_id"],
                "username": event["username"],
            })
        )

    async def participant_left(self, event):

        if event.get("sender_channel") == self.channel_name:
            return

        await self.send(
            text_data=json.dumps({
                "type": "participant_left",
                "user_id": event["user_id"],
            })
        )
        
    async def participant_rejected(self, event):

        if event.get("sender_channel") == self.channel_name:
            return

        await self.send(
            text_data=json.dumps({
                "type": "participant_rejected",
                "user_id": event["user_id"],
                "username": event.get("username"),
            })
        )
        
    async def call_ended(self, event):

        # ---------------------------------------------------------
        # CALL ENDED FOR EVERYONE
        # ---------------------------------------------------------

        await self.send(
            text_data=json.dumps({
                "type": "call_ended",
                "call_id": event["call_id"],
                "ended_by": event["ended_by"],
                "ended_by_username": event.get(
                    "ended_by_username"
                ),
            })
        )

    # =============================================================
    # DATABASE
    # =============================================================

    @database_sync_to_async
    def check_participant(self):

        from accounts.safety import blocked_user_ids
        if CallParticipant.objects.filter(call_id=self.call_id, user_id__in=blocked_user_ids(self.user)).exists():
            return False

        return CallParticipant.objects.filter(
            call_id=self.call_id,
            user=self.user,
            user__is_active=True,
            call__status__in=["RINGING", "ACTIVE"],
            call__conversation__participants__user=self.user,
            status__in=[
                "INVITED",
                "RINGING",
                "JOINED",
            ],
        ).exists()

    @database_sync_to_async
    def mark_participant_left(self):
        with transaction.atomic():
            call = Call.objects.select_for_update().filter(pk=self.call_id).first()
            if not call or call.status not in ('RINGING', 'ACTIVE'):
                return
            participant = CallParticipant.objects.filter(call=call, user=self.user, status__in=['INVITED', 'RINGING', 'JOINED']).first()
            if not participant:
                return
            participant.status = 'LEFT'
            participant.left_at = timezone.now()
            participant.save(update_fields=['status', 'left_at'])
            if (call.status == 'RINGING' and call.initiated_by_id == self.user.pk) or not CallParticipant.objects.filter(call=call, status__in=['INVITED', 'RINGING', 'JOINED']).exists():
                finish_call(call, self.user.pk)


class UserConsumer(SecureSocketMixin, AsyncWebsocketConsumer):
    @database_sync_to_async
    def messaging_access(self, conversation_id):
        from .realtime import can_access
        return can_access(self.user, conversation_id)

    async def messaging_event(self, event):
        import time
        if self.scope.get('jwt_expires_at', float('inf')) <= time.time():
            await self.close(code=4001)
            return
        if await self.messaging_access(event['data']['conversation_id']):
            await self.send(text_data=json.dumps(event['data']))

    async def call_ended(self, event):
        await self.send(text_data=json.dumps({
            'type': 'call_ended', 'call_id': event['call_id'],
            'status': event.get('status', 'ENDED'), 'ended_by': event.get('ended_by'),
        }))

    async def connect(self):

        self.user = self.scope["user"]

        # ---------------------------------------------------------
        # AUTHENTICATION
        # ---------------------------------------------------------

        if not await self.ensure_credentials():

            await self.close(code=4001)

            return

        # ---------------------------------------------------------
        # USER-SPECIFIC GROUP
        # ---------------------------------------------------------

        self.user_group_name = f"user_{self.user.id}"

        try:
            await self.channel_layer.group_add(
                self.user_group_name,
                self.channel_name
            )
        except RedisError as error:
            logger.warning(
                "Unable to register user WebSocket group for user %s.",
                self.user.id,
            )
            await self.close(code=1013)
            return

        # ---------------------------------------------------------
        # ACCEPT CONNECTION
        # ---------------------------------------------------------

        await self.accept()
        self.start_security_watchdog()

        # ---------------------------------------------------------
        # CONFIRM CONNECTION
        # ---------------------------------------------------------

        await self.send(
            text_data=json.dumps({
                "type": "user_connection",
                "reauthentication": True,
                "message": "Connected to Awinlink global event server.",
                "user_id": self.user.id,
            })
        )

    async def disconnect(self, close_code):

        self.stop_security_watchdog()

        if hasattr(self, "user_group_name"):

            try:
                await self.channel_layer.group_discard(
                    self.user_group_name,
                    self.channel_name
                )
            except RedisError as error:
                logger.warning(
                    "Unable to remove user WebSocket group for user %s.",
                    self.user.id,
                )

    async def receive(self, text_data=None, bytes_data=None):
        if not await self.bounded_frame(text_data, bytes_data) or not await self.ensure_credentials():
            return
        import time
        if self.scope.get('jwt_expires_at', float('inf')) <= time.time():
            await self.close(code=4001)
            return
        try:
            data = json.loads(text_data)
            if await self.reauthenticate(data):
                return
            if not isinstance(data, dict) or data.get('type') != 'typing':
                return
            conversation_id = int(data['conversation_id'])
            if type(data.get('is_typing')) is not bool:
                return
        except (ValueError, TypeError, KeyError, RecursionError):
            return
        if not await self.messaging_access(conversation_id):
            return
        now = time.monotonic()
        if data['is_typing'] and now - getattr(self, '_last_typing', 0) < 0.8:
            return
        self._last_typing = now
        from .realtime import publish
        await database_sync_to_async(publish)(conversation_id, {
            'type': 'typing', 'conversation_id': conversation_id,
            'user_id': self.user.pk, 'username': self.user.get_full_name() or self.user.username,
            'is_typing': data['is_typing'],
        })
    
    
    async def incoming_call(self, event):

        await self.send(
            text_data=json.dumps({
                "type": "incoming_call",
                "call_id": event["call_id"],
                "call_type": event["call_type"],
                "caller": {
                    "id": event["caller_id"],
                    "username": event["caller_username"],
                    "first_name": event["caller_first_name"],
                    "last_name": event["caller_last_name"],
                },
            })
        )

    async def notification_created(self, event):
        await self.send(
            text_data=json.dumps({
                "type": "notification_created",
                "notification": event["notification"],
            })
        )

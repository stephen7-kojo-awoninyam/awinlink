import json

from django.utils import timezone

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from .models import CallParticipant


class CallConsumer(AsyncWebsocketConsumer):

    async def connect(self):

        self.call_id = self.scope["url_route"]["kwargs"]["call_id"]
        self.user = self.scope["user"]

        # ---------------------------------------------------------
        # AUTHENTICATION
        # ---------------------------------------------------------

        if not self.user.is_authenticated:
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

        # ---------------------------------------------------------
        # CONFIRM CONNECTION
        # ---------------------------------------------------------

        await self.send(
            text_data=json.dumps({
                "type": "connection",
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

    async def receive(self, text_data):

        try:
            data = json.loads(text_data)

        except json.JSONDecodeError:

            await self.send(
                text_data=json.dumps({
                    "type": "error",
                    "message": "Invalid JSON."
                })
            )

            return


        # ---------------------------------------------------------
        # ADD SENDER INFORMATION
        # ---------------------------------------------------------

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

        return CallParticipant.objects.filter(
            call_id=self.call_id,
            user=self.user,
            status__in=[
                "INVITED",
                "RINGING",
                "JOINED",
            ],
        ).exists()

    @database_sync_to_async
    def mark_participant_left(self):

        participant = (
            CallParticipant.objects
            .select_related("call")
            .filter(
                call_id=self.call_id,
                user=self.user,
                status__in=[
                    "INVITED",
                    "RINGING",
                    "JOINED",
                ],
            )
            .first()
        )

        if not participant:
            return

        # ---------------------------------------------------------
        # MARK PARTICIPANT AS LEFT
        # ---------------------------------------------------------

        participant.status = "LEFT"
        participant.left_at = timezone.now()

        participant.save(
            update_fields=[
                "status",
                "left_at",
            ]
        )

        call = participant.call

        # ---------------------------------------------------------
        # CHECK WHETHER ANYONE IS STILL IN THE CALL
        # ---------------------------------------------------------

        remaining_participants = (
            CallParticipant.objects
            .filter(
                call=call,
                status__in=[
                    "INVITED",
                    "RINGING",
                    "JOINED",
                ],
            )
            .exclude(
                user=self.user
            )
            .exists()
        )

        # ---------------------------------------------------------
        # END CALL IF EVERYONE HAS LEFT
        # ---------------------------------------------------------

        if not remaining_participants:

            call.status = "ENDED"
            call.ended_at = timezone.now()

            # -----------------------------------------------------
            # CALCULATE DURATION
            # -----------------------------------------------------

            if call.answered_at:

                call.duration = int(
                    (
                        call.ended_at -
                        call.answered_at
                    ).total_seconds()
                )

            call.save(
                update_fields=[
                    "status",
                    "ended_at",
                    "duration",
                ]
            )
            
            
class UserConsumer(AsyncWebsocketConsumer):

    async def connect(self):

        self.user = self.scope["user"]

        # ---------------------------------------------------------
        # AUTHENTICATION
        # ---------------------------------------------------------

        if not self.user.is_authenticated:

            await self.close(code=4001)

            return

        # ---------------------------------------------------------
        # USER-SPECIFIC GROUP
        # ---------------------------------------------------------

        self.user_group_name = f"user_{self.user.id}"

        await self.channel_layer.group_add(
            self.user_group_name,
            self.channel_name
        )

        # ---------------------------------------------------------
        # ACCEPT CONNECTION
        # ---------------------------------------------------------

        await self.accept()

        # ---------------------------------------------------------
        # CONFIRM CONNECTION
        # ---------------------------------------------------------

        await self.send(
            text_data=json.dumps({
                "type": "user_connection",
                "message": "Connected to Awinlink global event server.",
                "user_id": self.user.id,
            })
        )

    async def disconnect(self, close_code):

        if hasattr(self, "user_group_name"):

            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name
            )

    async def receive(self, text_data):

        # ---------------------------------------------------------
        # GLOBAL USER SOCKET IS CURRENTLY RECEIVE-ONLY
        # ---------------------------------------------------------

        return   
    
    
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
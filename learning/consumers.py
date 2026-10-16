"""Peer-targeted classroom signaling; no dependency on call consumers."""

import asyncio
import json
import logging
import time
from time import monotonic as signaling_clock
from urllib.parse import parse_qs
from uuid import UUID

from channels.db import database_sync_to_async
from channels.exceptions import ChannelFull
from channels.generic.websocket import AsyncWebsocketConsumer
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.db import DatabaseError
from redis.exceptions import RedisError

from . import classroom_signaling as signaling
from .classroom_events import participant_group, session_group


logger = logging.getLogger(__name__)


class ClassroomConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.closing, self.bound, self.active = False, False, False
        self.watchdog = None
        self.joined_groups = []
        self.user = self.scope.get("user")
        self.claims = self.scope.get("jwt_claims") if self.scope.get("jwt_authenticated") else None
        self.session_key = getattr(self.scope.get("session"), "session_key", None)
        self.deadline = float(self.claims["exp"]) if self.claims is not None else None
        try:
            allowed = not self.scope.get("jwt_invalid") and getattr(self.user, "is_authenticated", False) and await self.credential_valid()
        except DatabaseError:
            await self.terminate(1013)
            return
        if not allowed:
            await self.terminate(4401)
            return
        try:
            self.session_id = int(self.scope["url_route"]["kwargs"]["session_id"])
            query = parse_qs(self.scope.get("query_string", b"").decode("ascii"), keep_blank_values=True, max_num_fields=4)
            if set(query) != {"connection_id"} or len(query["connection_id"]) != 1 or not 0 < self.session_id <= 9223372036854775807:
                raise ValueError()
            self.connection_id = UUID(query["connection_id"][0])
        except (KeyError, ValueError, UnicodeError):
            await self.terminate(4400)
            return
        self.room_group = session_group(self.session_id)
        try:
            result = await database_sync_to_async(signaling.prepare_connection)(
                actor=self.user, session_id=self.session_id, connection_id=self.connection_id, channel_name=self.channel_name)
            self.bound = True
            self.participant_id, self.role = result["participant_id"], result["role"]
            self.generation = signaling.public_generation(self.channel_name)
            self.peer_group = participant_group(self.session_id, self.participant_id)
            if self.channel_layer is None:
                raise RuntimeError("A Channels layer is required.")
            for group in [self.room_group, self.peer_group]:
                await self.channel_layer.group_add(group, self.channel_name)
                self.joined_groups.append(group)
            if not await self.credential_valid():
                await self.terminate(4401)
                return
            await database_sync_to_async(signaling.renew_connection)(**self.connection_args(), activate=True)
            await self.accept()
            self.active = True
            self.tokens, self.last_refill = 60.0, signaling_clock()
            self.last_peers = await database_sync_to_async(signaling.peers)(self.session_id, self.participant_id)
            await self.send_json({"type": "connection", "session_id": self.session_id, "participant_id": self.participant_id,
                "user_id": self.user.pk, "role": self.role, "generation": self.generation,
                "connection_id": str(self.connection_id), "peers": self.last_peers})
            self.watchdog = asyncio.create_task(self.run_watchdog())
        except SignalingErrors as exc:
            code = 4410 if isinstance(exc, signaling.SignalingDenied) and exc.reason == "ended" else 4403
            if isinstance(exc, ObjectDoesNotExist):
                code = 4404
            await self.terminate(code)
        except (RedisError, ChannelFull, OSError, RuntimeError, DatabaseError):
            logger.exception("Classroom signaling connection failed for session %s.", self.session_id)
            await self.terminate(1013)

    def connection_args(self):
        return {"session_id": self.session_id, "user_id": self.user.pk,
                "connection_id": self.connection_id, "channel_name": self.channel_name}

    async def credential_valid(self):
        if self.deadline is not None and time.time() >= self.deadline:
            return False
        return await database_sync_to_async(signaling.credential_valid)(self.user.pk, claims=self.claims, session_key=self.session_key)

    async def authorized(self):
        if self.closing:
            return False
        try:
            if not await self.credential_valid():
                await self.terminate(4401)
                return False
            state = await database_sync_to_async(signaling.connection_state)(**self.connection_args())
        except DatabaseError:
            await self.terminate(1013)
            return False
        if state != "authorized":
            code = {"ended": 4410, "removed": 4403, "replaced": 4409}[state]
            await self.terminate(code, state)
            return False
        return True

    async def receive(self, text_data=None, bytes_data=None):
        if self.closing or not self.active:
            return
        now = signaling_clock()
        self.tokens = min(60, self.tokens + (now - self.last_refill) * 20)
        self.last_refill = now
        if self.tokens < 1:
            await self.terminate(4408)
            return
        self.tokens -= 1
        if not await self.authorized():
            return
        if bytes_data is not None:
            await self.terminate(1003)
            return
        try:
            if text_data is None or len(text_data.encode("utf-8")) > signaling.MAX_FRAME_BYTES:
                await self.terminate(1009)
                return
            data = signaling.parse_message(text_data)
        except (ValueError, TypeError, RecursionError, UnicodeError):
            await self.send_json({"type": "error", "code": "invalid_message", "detail": "Invalid classroom signaling message."})
            return
        if data["type"] == "ping":
            await self.send_json({"type": "pong"})
            return
        if data["recipient_id"] == self.participant_id:
            await self.send_json({"type": "error", "code": "invalid_recipient", "detail": "A connected admitted peer is required."})
            return
        recipient = await database_sync_to_async(signaling.recipient_connection)(self.session_id, data["recipient_id"])
        if recipient is None:
            await self.send_json({"type": "error", "code": "invalid_recipient", "detail": "A connected admitted peer is required."})
            return
        payload = {**data, "session_id": self.session_id, "sender_id": self.user.pk,
                   "sender_participant_id": self.participant_id, "sender_generation": self.generation}
        try:
            await self.channel_layer.group_send(participant_group(self.session_id, data["recipient_id"]), {
                "type": "classroom_signal", "session_id": self.session_id, "payload": payload,
                "sender_id": self.participant_id, "sender_connection": str(self.connection_id), "sender_channel": self.channel_name,
                "sender_deadline": self.deadline, "recipient_id": data["recipient_id"],
                "recipient_connection": str(recipient["connection_id"]), "recipient_channel": recipient["signaling_channel_name"],
            })
        except (RedisError, ChannelFull, OSError):
            await self.terminate(1013)

    async def classroom_signal(self, event):
        if event.get("session_id") != self.session_id or event.get("recipient_id") != self.participant_id or event.get("recipient_channel") != self.channel_name or event.get("recipient_connection") != str(self.connection_id):
            return
        if not await self.authorized() or (event.get("sender_deadline") is not None and time.time() >= event["sender_deadline"]):
            return
        current = await database_sync_to_async(signaling.relay_is_current)(self.session_id,
            event["sender_id"], event["sender_connection"], event["sender_channel"], event["recipient_id"],
            event["recipient_connection"], event["recipient_channel"])
        if current and (event.get("sender_deadline") is None or time.time() < event["sender_deadline"]):
            await self.send_json(event["payload"])

    async def classroom_control(self, event):
        if event.get("session_id") == self.session_id and await self.authorized():
            await self.presence()

    async def presence(self):
        peers = await database_sync_to_async(signaling.peers)(self.session_id, self.participant_id)
        if peers != self.last_peers:
            self.last_peers = peers
            await self.send_json({"type": "presence", "session_id": self.session_id, "peers": peers})

    async def classroom_tick(self, event):
        if not await self.authorized():
            return
        try:
            await database_sync_to_async(signaling.renew_connection)(**self.connection_args())
            for group in self.joined_groups:
                await self.channel_layer.group_add(group, self.channel_name)
            await self.presence()
        except signaling.SignalingDenied as exc:
            await self.terminate({"ended": 4410, "removed": 4403, "replaced": 4409}[exc.reason], exc.reason)
        except (RedisError, ChannelFull, OSError):
            await self.terminate(1013)

    async def run_watchdog(self):
        try:
            while not self.closing:
                delay = signaling.heartbeat_seconds()
                if self.deadline is not None:
                    delay = min(delay, max(0.01, self.deadline - time.time()))
                await asyncio.sleep(delay)
                await self.channel_layer.send(self.channel_name, {"type": "classroom_tick"})
        except asyncio.CancelledError:
            pass
        except (RedisError, ChannelFull, OSError):
            await self.terminate(1013)

    async def terminate(self, code, reason=None):
        if self.closing:
            return
        self.closing = True
        if self.active and reason:
            await self.send_json({"type": {"ended": "session_ended", "removed": "removed", "replaced": "replaced"}[reason],
                                  "session_id": self.session_id})
        await self.cleanup()
        await self.close(code=code)

    async def cleanup(self):
        if self.watchdog is not None and self.watchdog is not asyncio.current_task():
            self.watchdog.cancel()
        if self.bound:
            try:
                await database_sync_to_async(signaling.disconnect_connection)(**self.connection_args())
            except DatabaseError:
                logger.exception("Unable to close classroom attendance for session %s.", self.session_id)
        for group in self.joined_groups:
            try:
                await self.channel_layer.group_discard(group, self.channel_name)
            except (RedisError, OSError):
                pass

    async def disconnect(self, code):
        if not self.closing:
            self.closing = True
            await self.cleanup()

    async def send_json(self, data):
        # Database awaits may cross the token deadline. Check again immediately
        # before emitting anything, not only when a queued event was received.
        if self.deadline is not None and time.time() >= self.deadline:
            if not self.closing:
                await self.terminate(4401)
            return
        await self.send(text_data=json.dumps(data))


SignalingErrors = (PermissionDenied, ValidationError, ObjectDoesNotExist, signaling.SignalingDenied)

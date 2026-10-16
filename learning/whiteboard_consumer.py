"""Independent whiteboard transport; never acquires a signaling connection lease."""
import asyncio
import json
import logging
import time
from time import monotonic as whiteboard_clock

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError

from . import classroom_signaling as authentication
from . import whiteboard_services as services
from . import classroom_chat as chat
from .classroom_events import session_group


logger = logging.getLogger(__name__)


class WhiteboardConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.closing = False
        self.groups_joined = []
        self.watchdog = None
        self.last_snapshot = None
        self.chat_cursor = None
        self.tokens, self.refill_at = 30., whiteboard_clock()
        self.user = self.scope.get("user")
        self.claims = self.scope.get("jwt_claims") if self.scope.get("jwt_authenticated") else None
        self.session_key = getattr(self.scope.get("session"), "session_key", None)
        try:
            if self.scope.get("query_string"):
                await self.finish(4400)
                return
            if not await self.authenticated():
                await self.finish(4401)
                return
            self.session_id = int(self.scope["url_route"]["kwargs"]["session_id"])
            if self.session_id > 9223372036854775807:
                await self.finish(4400)
                return
            # Subscribe before reading to avoid missing a commit during connection.
            for room in [services.group(self.session_id), session_group(self.session_id)]:
                await self.channel_layer.group_add(room, self.channel_name)
                self.groups_joined.append(room)
            state = await database_sync_to_async(services.snapshot)(actor=self.user, session_id=self.session_id)
            if not await self.authenticated():
                await self.finish(4401)
                return
            await self.accept()
            await self.send_state(state)
            self.watchdog = asyncio.create_task(self.watch())
        except ObjectDoesNotExist:
            await self.finish(4404)
        except PermissionDenied:
            await self.finish(4403)
        except Exception:
            logger.exception("Whiteboard connection failed")
            await self.finish(1013)

    async def authenticated(self):
        if self.scope.get("jwt_invalid") or not getattr(self.user, "is_authenticated", False):
            return False
        return await database_sync_to_async(authentication.credential_valid)(
            self.user.pk, claims=self.claims, session_key=self.session_key)

    async def send_json(self, value):
        if self.closing:
            return
        if self.claims and float(self.claims["exp"]) <= time.time():
            await self.finish(4401)
            return
        await self.send(text_data=json.dumps(value, allow_nan=False))

    async def send_state(self, state):
        self.last_snapshot = (state["revision"], state["can_edit"], state["can_manage"])
        await self.send_json({"type": "snapshot", **state})

    async def receive(self, text_data=None, bytes_data=None):
        if self.closing:
            return
        if bytes_data is not None:
            await self.finish(1003)
            return
        if text_data is None or len(text_data.encode()) > 65536:
            await self.finish(1009)
            return
        now = whiteboard_clock()
        self.tokens = min(30., self.tokens + (now - self.refill_at) * 10)
        self.refill_at = now
        if self.tokens < 1:
            await self.finish(4408)
            return
        self.tokens -= 1
        try:
            if not await self.authenticated():
                await self.finish(4401)
                return
            data = json.loads(text_data, object_pairs_hook=authentication._unique_keys,
                              parse_constant=authentication._reject_constant)
            if isinstance(data, dict) and data.get("type") == "chat" and set(data) == {"type", "client_id", "text"}:
                result = await database_sync_to_async(chat.send)(actor=self.user, session_id=self.session_id,
                    data={"client_id": data["client_id"], "text": data["text"]})
                await self.send_json({"type": "chat", "message": result})
                return
            if isinstance(data, dict) and data.get("type") == "chat_history" and set(data) <= {"type", "after"}:
                await self.sync_chat(after=data.get("after", 0), force=True)
                return
            if data == {"type": "snapshot"}:
                await self.refresh(force=True)
                return
            result = await database_sync_to_async(services.command)(
                actor=self.user, session_id=self.session_id, data=data)
            await self.send_json({"type": "ack", **result})
            await self.refresh()
        except services.RevisionConflict:
            await self.send_json({"type": "error", "code": "conflict"})
            await self.refresh(force=True)
        except (ValidationError, ValueError, TypeError, RecursionError):
            await self.send_json({"type": "error", "code": "invalid_request"})
        except PermissionDenied:
            # A read-only learner stays connected; a removed learner is closed by refresh.
            await self.send_json({"type": "error", "code": "permission_denied"})
            await self.refresh()
        except Exception:
            logger.exception("Whiteboard command failed")
            await self.finish(1013)

    async def refresh(self, force=False):
        if self.closing:
            return
        try:
            if not await self.authenticated():
                await self.finish(4401)
                return
            state = await database_sync_to_async(services.snapshot)(actor=self.user, session_id=self.session_id)
            marker = (state["revision"], state["can_edit"], state["can_manage"])
            if force or marker != self.last_snapshot:
                await self.send_state(state)
        except (PermissionDenied, ObjectDoesNotExist):
            await self.finish(4403)
        except Exception:
            logger.exception("Whiteboard refresh failed")
            await self.finish(1013)

    async def whiteboard_changed(self, event):
        await self.refresh()

    async def classroom_control(self, event):
        await self.refresh()

    async def classroom_chat(self, event):
        if self.closing:
            return
        try:
            if not await self.authenticated():
                await self.finish(4401)
                return
            if self.chat_cursor is not None:
                await self.sync_chat()
                return
            message = await database_sync_to_async(chat.delivery)(actor=self.user, session_id=self.session_id,
                message_id=event["message_id"])
            await self.send_json({"type": "chat", "message": message})
        except (PermissionDenied, ObjectDoesNotExist):
            await self.refresh()
        except Exception:
            logger.exception("Classroom chat delivery failed")
            await self.finish(1013)

    async def sync_chat(self, *, after=None, force=False):
        if self.closing:
            return
        # A cursor moves only through ordered, authorized database reads. A newer
        # broadcast must not skip messages whose Redis notification was lost.
        page = await database_sync_to_async(chat.history_page)(actor=self.user,
            session_id=self.session_id, after=self.chat_cursor if after is None else after)
        self.chat_cursor = page["next_after"]
        if force or page["results"]:
            await self.send_json({"type": "chat_history", "messages": page["results"],
                "next_after": page["next_after"], "has_more": page["has_more"]})

    async def whiteboard_tick(self, event):
        try:
            for room in self.groups_joined:
                await self.channel_layer.group_add(room, self.channel_name)
            await self.refresh()
            if not self.closing and self.chat_cursor is not None:
                await self.sync_chat()
        except Exception:
            logger.exception("Whiteboard channel lease refresh failed")
            await self.finish(1013)

    async def watch(self):
        try:
            while not self.closing:
                delay = authentication.heartbeat_seconds()
                if self.claims:
                    delay = min(delay, max(.01, float(self.claims["exp"]) - time.time()))
                await asyncio.sleep(delay)
                await self.channel_layer.send(self.channel_name, {"type": "whiteboard_tick"})
        except asyncio.CancelledError:
            pass
        except Exception:
            await self.finish(1013)

    async def finish(self, code=None):
        if self.closing:
            return
        self.closing = True
        if self.watchdog and self.watchdog is not asyncio.current_task():
            self.watchdog.cancel()
        for room in self.groups_joined:
            try:
                await self.channel_layer.group_discard(room, self.channel_name)
            except Exception:
                logger.warning("Whiteboard room cleanup failed")
        if code is not None:
            await self.close(code=code)

    async def disconnect(self, code):
        await self.finish()

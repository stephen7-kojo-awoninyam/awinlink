"""Credential revocation and bounded input for existing session/JWT sockets."""
import asyncio
import time

from channels.db import database_sync_to_async
from django.conf import settings
from django.db import DatabaseError
from redis.exceptions import RedisError


class SecureSocketMixin:
    async def close(self, *args, **kwargs):
        self.stop_security_watchdog()
        return await super().close(*args, **kwargs)

    async def credentials_valid(self):
        from learning.classroom_signaling import credential_valid
        scope = self.scope
        if scope.get('jwt_invalid') or not getattr(self.user, 'is_authenticated', False):
            return False
        claims = scope.get('jwt_claims') if scope.get('jwt_authenticated') else None
        session_key = getattr(scope.get('session'), 'session_key', None)
        try:
            return await database_sync_to_async(credential_valid)(self.user.pk, claims=claims, session_key=session_key)
        except (DatabaseError, RedisError):
            return False

    async def ensure_credentials(self):
        if not await self.credentials_valid():
            await self.close(code=4001)
            return False
        return True

    async def delivery_allowed(self):
        return True

    async def send(self, *args, **kwargs):
        if not await self.ensure_credentials():
            return
        if not await self.delivery_allowed():
            await self.close(code=4003)
            return
        return await super().send(*args, **kwargs)

    def start_security_watchdog(self):
        self._security_task = asyncio.create_task(self.security_watchdog())

    def stop_security_watchdog(self):
        task = getattr(self, '_security_task', None)
        if task is not None and task is not asyncio.current_task():
            task.cancel()

    async def security_watchdog(self):
        try:
            while True:
                delay = max(0.05, float(getattr(settings, 'MESSAGING_WS_HEARTBEAT_SECONDS', 5)))
                deadline = self.scope.get('jwt_expires_at')
                if deadline is not None:
                    delay = min(delay, max(0.01, deadline - time.time()))
                await asyncio.sleep(delay)
                await self.channel_layer.send(self.channel_name, {'type': 'security_tick'})
        except asyncio.CancelledError:
            pass
        except (OSError, RedisError):
            await self.close(code=1013)

    async def security_tick(self, event):
        if await self.ensure_credentials() and not await self.delivery_allowed():
            await self.close(code=4003)

    async def bounded_frame(self, text_data, bytes_data):
        if bytes_data is not None:
            await self.close(code=1003)
            return False
        if text_data is None or len(text_data.encode('utf-8')) > 65536:
            await self.close(code=1009)
            return False
        now = time.monotonic()
        tokens = min(60., getattr(self, '_security_tokens', 60.) + (now - getattr(self, '_security_refill', now)) * 20)
        self._security_refill, self._security_tokens = now, tokens - 1
        if tokens < 1:
            await self.close(code=4008)
            return False
        return True

    async def reauthenticate(self, data):
        if not isinstance(data, dict) or data.get('type') != 'reauthenticate':
            return False
        from config.asgi import _jwt_socket_identity
        token = data.get('access')
        identity = await _jwt_socket_identity(token) if isinstance(token, str) and len(token) <= 16384 else None
        if not self.scope.get('jwt_authenticated') or identity is None or identity[0].pk != self.user.pk:
            await self.close(code=4001)
            return True
        self.scope = {**self.scope, 'jwt_claims': identity[1], 'jwt_expires_at': identity[1]['exp']}
        return True

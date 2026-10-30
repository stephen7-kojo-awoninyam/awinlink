"""Account-wide protection for every WebSocket transport after authentication."""
import asyncio
from contextlib import suppress
from types import SimpleNamespace

from asgiref.sync import sync_to_async

from .resource_limits import Lease, ResourceLimited, ResourceUnavailable, consume


def transport_codes(scope):
    # Retain the classroom protocol's existing error-code family.
    if scope.get('path', '').startswith('/ws/learning/sessions/'):
        return {'limited': 4408, 'unavailable': 4503, 'binary': 4400, 'oversized': 4400}
    return {'limited': 4008, 'unavailable': 1013, 'binary': 1003, 'oversized': 1009}


class SocketHandshakeLimits:
    """Bound credential verification work before session/JWT authentication."""
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        from accounts.recovery import client_address
        peer = scope.get('client') or ('unknown', 0)
        meta = {'HTTP_' + key.decode('latin1').upper().replace('-', '_'): value.decode('latin1')
                for key, value in scope.get('headers', [])}
        meta['REMOTE_ADDR'] = peer[0]
        identity = client_address(SimpleNamespace(META=meta))
        try:
            await sync_to_async(consume, thread_sensitive=False)('ws_handshakes', identity)
        except (ResourceLimited, ResourceUnavailable) as exc:
            codes = transport_codes(scope)
            return await send({'type': 'websocket.close', 'code': codes['limited' if isinstance(exc, ResourceLimited) else 'unavailable']})
        return await self.inner(scope, receive, send)


class SharedSocketLimits:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        user = scope.get('user')
        if scope.get('jwt_invalid') or not getattr(user, 'is_authenticated', False):
            return await self.inner(scope, receive, send)
        lease = cluster_lease = None
        app = watch = None
        acquisitions = []
        closed = False
        codes = transport_codes(scope)
        stopping = asyncio.Event()

        async def close(code):
            nonlocal closed
            if not closed:
                closed = True
                await send({'type': 'websocket.close', 'code': code})

        async def guarded_send(message):
            nonlocal closed
            if not closed:
                if message['type'] == 'websocket.close':
                    closed = True
                await send(message)

        async def guarded_receive():
            incoming = asyncio.create_task(receive())
            stopped = asyncio.create_task(stopping.wait())
            try:
                done, _ = await asyncio.wait([incoming, stopped], return_when=asyncio.FIRST_COMPLETED)
                if stopped in done:
                    return {'type': 'websocket.disconnect', 'code': codes['unavailable']}
                message = await incoming
            finally:
                for pending in (incoming, stopped):
                    if not pending.done():
                        pending.cancel()
                    with suppress(asyncio.CancelledError):
                        await pending
            if message['type'] == 'websocket.receive':
                text = message.get('text')
                if message.get('bytes') is not None or text is None or len(text) > 65536 or len(text.encode('utf-8')) > 65536:
                    code = codes['oversized' if text is not None else 'binary']
                    await close(code)
                    return {'type': 'websocket.disconnect', 'code': code}
                try:
                    await sync_to_async(consume, thread_sensitive=False)('ws_frames', user.pk)
                except (ResourceLimited, ResourceUnavailable) as exc:
                    code = codes['limited' if isinstance(exc, ResourceLimited) else 'unavailable']
                    await close(code)
                    return {'type': 'websocket.disconnect', 'code': code}
            return message

        async def renew():
            while True:
                await asyncio.sleep(max(0.1, min(lease.ttl, cluster_lease.ttl) / 3))
                await sync_to_async(lease.renew, thread_sensitive=False)()
                await sync_to_async(cluster_lease.renew, thread_sensitive=False)()

        async def acquire(item):
            # A canceled async wrapper cannot cancel an in-flight Redis command.
            # Drain it before release, so a late ZADD cannot strand a lease.
            operation = asyncio.create_task(sync_to_async(item.acquire, thread_sensitive=False)())
            acquisitions.append(operation)
            return await asyncio.shield(operation)

        try:
            await sync_to_async(consume, thread_sensitive=False)('ws_connects', user.pk)
            lease = Lease('ws_connections', user.pk)
            await acquire(lease)
            cluster_lease = Lease('ws_global_connections', 'cluster')
            await acquire(cluster_lease)
            app = asyncio.create_task(self.inner(scope, guarded_receive, guarded_send))
            watch = asyncio.create_task(renew())
            done, _ = await asyncio.wait([app, watch], return_when=asyncio.FIRST_COMPLETED)
            if watch in done:
                await watch
            else:
                await app
        except (ResourceLimited, ResourceUnavailable) as exc:
            await close(codes['limited' if isinstance(exc, ResourceLimited) else 'unavailable'])
        finally:
            try:
                # Deliver a disconnect so classroom presence/group cleanup run.
                stopping.set()
                if app is not None and not app.done():
                    with suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(asyncio.shield(app), timeout=2)
            finally:
                try:
                    tasks = [task for task in (watch, app) if task is not None]
                    for task in tasks:
                        if not task.done(): task.cancel()
                    # Retrieve errors even when consumer and watchdog finish in
                    # the same event-loop tick; never leave orphaned tasks.
                    await asyncio.gather(*tasks, *acquisitions, return_exceptions=True)
                finally:
                    for held in (lease, cluster_lease):
                        if held is not None:
                            with suppress(ResourceUnavailable):
                                await sync_to_async(held.release, thread_sensitive=False)()

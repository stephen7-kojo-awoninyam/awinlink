"""Bound request bodies before Django ASGI can buffer them to disk."""
import asyncio
from contextlib import suppress
import json
import math
import time

from asgiref.sync import sync_to_async
from django.conf import settings
from rest_framework.exceptions import APIException

from .resource_limits import Lease, ResourceUnavailable


class BodyRejected(APIException):
    def __init__(self, detail, status=413):
        self.status_code = status
        super().__init__(detail)


def body_limit(content_type):
    multipart = content_type.split(';', 1)[0].strip().lower() == 'multipart/form-data'
    values = ([getattr(settings, 'AWINLINK_UPLOAD_TOTAL_BYTES', 250 * 1024 * 1024),
               getattr(settings, 'AWINLINK_UPLOAD_OVERHEAD_BYTES', 5 * 1024 * 1024)] if multipart
              else [getattr(settings, 'AWINLINK_JSON_BODY_BYTES', 2621440)])
    if any(type(value) is not int or value <= 0 for value in values):
        raise ResourceUnavailable()
    return multipart, sum(values)


def check_length(value, limit):
    try:
        length = int(value or 0)
        if length < 0: raise ValueError()
    except (TypeError, ValueError):
        raise BodyRejected('Invalid request length.', 400) from None
    if length > limit:
        raise BodyRejected('Request is too large. Send fewer items or a smaller file.')


class HTTPBodyLimits:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        scope = dict(scope)
        headers = dict(scope.get('headers', []))
        lease = acquisition = None
        failure = None
        started = body_done = False
        total = 0
        last_data = began = time.monotonic()

        async def error(exception):
            payload = json.dumps({'detail': str(exception.detail)}).encode()
            response_headers = [(b'content-type', b'application/json'), (b'content-length', str(len(payload)).encode()),
                                (b'cache-control', b'private, no-store'), (b'x-content-type-options', b'nosniff')]
            if getattr(exception, 'wait', None):
                response_headers.append((b'retry-after', str(exception.wait).encode()))
            await send({'type': 'http.response.start', 'status': exception.status_code, 'headers': response_headers})
            await send({'type': 'http.response.body', 'body': payload})

        async def guarded_send(message):
            nonlocal started
            if message['type'] == 'http.response.start': started = True
            await send(message)

        async def guarded_receive():
            nonlocal total, last_data, body_done, failure, renew_at
            if failure is not None: return {'type': 'http.disconnect'}
            while True:
                now = time.monotonic()
                if lease is None:
                    message = await receive()
                    break
                if now - began >= duration or (not body_done and now - last_data >= idle):
                    failure = BodyRejected('Upload timed out. Please retry.', 408)
                    return {'type': 'http.disconnect'}
                if now >= renew_at:
                    try:
                        await sync_to_async(lease.renew, thread_sensitive=False)()
                    except APIException as exc:
                        failure = exc
                        return {'type': 'http.disconnect'}
                    renew_at = time.monotonic() + lease.ttl / 3
                timeout = min(lease.ttl / 3, duration - (now - began), idle if body_done else idle - (now - last_data))
                try:
                    message = await asyncio.wait_for(receive(), timeout=max(.01, timeout))
                    break
                except asyncio.TimeoutError:
                    continue
            if message['type'] == 'http.request':
                chunk = message.get('body', b'')
                total += len(chunk)
                if total > limit:
                    failure = BodyRejected('Request is too large. Send fewer items or a smaller file.')
                    # Django read_body closes its spool on disconnect. Returning
                    # a disconnect also stops later view/storage work entirely.
                    return {'type': 'http.disconnect'}
                if chunk: last_data = time.monotonic()
                body_done = not message.get('more_body', False)
                if body_done and b'content-length' not in headers:
                    # Django's multipart/DRF parsers need a length even when the
                    # ASGI server received an otherwise valid chunked upload.
                    scope['headers'] = [*scope.get('headers', []), (b'content-length', str(total).encode())]
            return message

        try:
            multipart, limit = body_limit(headers.get(b'content-type', b'').decode('latin1'))
            check_length(headers.get(b'content-length'), limit)
            if multipart:
                idle = getattr(settings, 'AWINLINK_UPLOAD_IDLE_SECONDS', 120)
                duration = getattr(settings, 'AWINLINK_UPLOAD_REQUEST_SECONDS', 3600)
                if (any(type(value) not in (int, float) or not math.isfinite(value) for value in (idle, duration))
                        or not 0 < idle <= duration):
                    raise ResourceUnavailable()
                lease = Lease('upload_global', 'cluster')
                acquisition = asyncio.create_task(sync_to_async(lease.acquire, thread_sensitive=False)())
                await asyncio.shield(acquisition)
                renew_at = time.monotonic() + lease.ttl / 3
                scope['_awinlink_upload_global_lease'] = lease
            await self.inner(scope, guarded_receive, guarded_send)
            if failure is not None and not started: await error(failure)
        except APIException as exc:
            if started: raise
            await error(exc)
        finally:
            if acquisition is not None:
                await asyncio.gather(acquisition, return_exceptions=True)
            if lease is not None:
                with suppress(ResourceUnavailable):
                    await sync_to_async(lease.release, thread_sensitive=False)()

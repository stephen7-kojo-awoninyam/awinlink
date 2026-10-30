import asyncio
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch

from asgiref.sync import async_to_sync
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.testing import WebsocketCommunicator
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from .resource_limits import Lease, ResourceLimited, ResourceUnavailable, consume
from .socket_limits import SharedSocketLimits, SocketHandshakeLimits


LIMITS = {
    'bytes': (100, 3600), 'slots': (3, 2),
    'ws_connections': (3, 2), 'ws_connects': (100, 60), 'ws_frames': (3, 3600),
    'ws_global_connections': (20, 2),
}


@override_settings(DEBUG=True, HOSTED_PRODUCTION=False, AWINLINK_RESOURCE_CACHE_ALIAS='default', AWINLINK_RESOURCE_LIMITS=LIMITS)
class AtomicResourceTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_concurrent_consumers_cannot_overspend_bytes(self):
        def attempt(_):
            try:
                consume('bytes', 'account', 10)
                return True
            except ResourceLimited:
                return False
        with ThreadPoolExecutor(max_workers=16) as pool:
            self.assertEqual(sum(pool.map(attempt, range(50))), 10)
        consume('bytes', 'different-account', 100)

    def test_atomic_slots_release_is_idempotent_and_cannot_release_other_lease(self):
        leases = [Lease('slots', 'account').acquire() for _ in range(3)]
        with self.assertRaises(ResourceLimited):
            Lease('slots', 'account').acquire()
        leases[0].release(); leases[0].release()
        replacement = Lease('slots', 'account').acquire()
        leases[0].release()
        with self.assertRaises(ResourceLimited):
            Lease('slots', 'account').acquire()
        replacement.renew()

    def test_crashed_worker_expires_and_stale_owner_cannot_renew(self):
        with patch('config.resource_limits.time.monotonic', return_value=100):
            old = Lease('slots', 'account').acquire()
        with patch('config.resource_limits.time.monotonic', return_value=103):
            with self.assertRaises(ResourceLimited):
                old.renew()
            self.assertIsNotNone(Lease('slots', 'account').acquire())

    def test_refill_preserves_fractional_tokens_and_does_not_reset_on_denial(self):
        with patch('config.resource_limits.time.monotonic', return_value=100):
            consume('bytes', 'account', 100)
        with patch('config.resource_limits.time.monotonic', return_value=118):
            with self.assertRaises(ResourceLimited): consume('bytes', 'account', 1)
        with patch('config.resource_limits.time.monotonic', return_value=136):
            consume('bytes', 'account', 1)
            with self.assertRaises(ResourceLimited): consume('bytes', 'account', 1)

    @override_settings(DEBUG=False, AWINLINK_ENV='production')
    def test_production_never_uses_local_cache(self):
        with self.assertRaises(ResourceUnavailable): consume('bytes', 'account')
        with self.assertRaises(ResourceUnavailable): Lease('slots', 'account').acquire()

    def test_cache_outage_fails_closed_without_connection_details(self):
        with patch('config.resource_limits._backend', side_effect=RuntimeError('redis://secret')):
            for operation in (lambda: consume('bytes', 'account'), lambda: Lease('slots', 'account').acquire()):
                with self.assertRaises(ResourceUnavailable) as raised: operation()
                self.assertNotIn('secret', str(raised.exception))

    def test_invalid_policies_fail_closed(self):
        for values in ((0, 60), (-1, 60), (True, 60), (10, '60'), (10,)):
            with self.subTest(values=values), override_settings(AWINLINK_RESOURCE_LIMITS={'bytes': values}):
                with self.assertRaises(ResourceUnavailable): consume('bytes', 'account')

    def test_production_resource_check_requires_redis_without_network_probes(self):
        from .deployment_checks import shared_resource_cache
        with override_settings(DEBUG=False, AWINLINK_ENV='production'):
            self.assertEqual(shared_resource_cache(None)[0].id, 'awinlink.E003')
            with override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.redis.RedisCache',
                                                     'LOCATION': 'redis://127.0.0.1:9/0'}}), \
                    patch('redis.Redis.execute_command', side_effect=AssertionError('No live probe')):
                self.assertEqual(shared_resource_cache(None), [])


class Echo(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()

    async def receive(self, text_data=None, bytes_data=None):
        await self.send(text_data=text_data)


@override_settings(DEBUG=True, HOSTED_PRODUCTION=False, AWINLINK_RESOURCE_CACHE_ALIAS='default', AWINLINK_RESOURCE_LIMITS=LIMITS)
class SharedSocketTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def socket(self, path='/ws/user/', user=1, inner=None):
        socket = WebsocketCommunicator(SharedSocketLimits(inner or Echo.as_asgi()), path)
        socket.scope['user'] = SimpleNamespace(pk=user, is_authenticated=True)
        return socket

    @override_settings(AWINLINK_RESOURCE_LIMITS={**LIMITS, 'ws_handshakes': (2, 3600)},
                       PASSWORD_RESET_TRUSTED_IP_HEADER='', PASSWORD_RESET_TRUSTED_PROXY_COUNT=0)
    def test_pre_auth_handshake_budget_ignores_spoofed_forwarded_addresses(self):
        async def run():
            for index in range(3):
                socket = WebsocketCommunicator(SocketHandshakeLimits(Echo.as_asgi()), '/ws/',
                    headers=[(b'x-forwarded-for', f'10.0.0.{index}'.encode())])
                socket.scope['client'] = ('127.0.0.1', 1234)
                accepted = await socket.connect()
                self.assertEqual(accepted[0], index < 2)
                if index == 2: self.assertEqual(accepted[1], 4008)
                await socket.disconnect()
        async_to_sync(run)()

    def test_frames_are_aggregated_across_transports_and_connections(self):
        async def run():
            first, second = self.socket(), self.socket('/ws/classroom/')
            self.assertTrue((await first.connect())[0]); self.assertTrue((await second.connect())[0])
            for socket in (first, second, first):
                await socket.send_to(text_data='{}'); self.assertEqual(await socket.receive_from(), '{}')
            await second.send_to(text_data='{}')
            self.assertEqual((await second.receive_output())['code'], 4008)
            other = self.socket(user=2); self.assertTrue((await other.connect())[0])
            await other.send_to(text_data='{}'); self.assertEqual(await other.receive_from(), '{}')
            await first.disconnect(); await second.disconnect(); await other.disconnect()
        async_to_sync(run)()

    def test_connections_are_shared_and_disconnect_releases_slot(self):
        async def run():
            sockets = [self.socket('/ws/' + str(n)) for n in range(4)]
            accepted = await asyncio.gather(*(socket.connect() for socket in sockets))
            self.assertEqual(sum(result[0] for result in accepted), 3)
            winner = next(socket for socket, result in zip(sockets, accepted) if result[0])
            await winner.disconnect()
            replacement = self.socket(); self.assertTrue((await replacement.connect())[0])
            await replacement.disconnect()
            for socket in sockets:
                if socket is not winner: await socket.disconnect()
        async_to_sync(run)()

    def test_oversized_binary_frames_and_unavailable_backend_are_closed(self):
        async def run():
            for message, code in (({'text_data': 'x' * 65537}, 1009), ({'bytes_data': b'x'}, 1003)):
                socket = self.socket(); self.assertTrue((await socket.connect())[0])
                await socket.send_to(**message); self.assertEqual((await socket.receive_output())['code'], code)
                await socket.disconnect()
            with patch('config.socket_limits.consume', side_effect=ResourceUnavailable()):
                socket = self.socket(); self.assertEqual(await socket.connect(), (False, 1013))
                await socket.disconnect()
        async_to_sync(run)()

    def test_watchdog_renews_idle_lease_and_runs_consumer_cleanup_on_failure(self):
        cleaned = []
        class CleanEcho(Echo):
            async def disconnect(self, code): cleaned.append(code)
        async def run():
            socket = self.socket(inner=CleanEcho.as_asgi()); self.assertTrue((await socket.connect())[0])
            with patch('config.socket_limits.Lease.renew', side_effect=ResourceUnavailable()):
                self.assertEqual((await socket.receive_output(timeout=2))['code'], 1013)
                await socket.wait(timeout=2)
            self.assertTrue(cleaned)
            await socket.disconnect()
        async_to_sync(run)()

    @override_settings(AWINLINK_RESOURCE_LIMITS={**LIMITS, 'ws_global_connections': (1, 2)})
    def test_cluster_capacity_is_shared_between_different_accounts(self):
        async def run():
            first, second = self.socket(user=1), self.socket(user=2)
            self.assertTrue((await first.connect())[0])
            self.assertEqual(await second.connect(), (False, 4008))
            await second.disconnect(); await first.disconnect()
            replacement = self.socket(user=2)
            self.assertTrue((await replacement.connect())[0]); await replacement.disconnect()
        async_to_sync(run)()

    @override_settings(AWINLINK_RESOURCE_LIMITS={**LIMITS, 'ws_connections': (3, 30)})
    def test_cancel_during_acquisition_drains_late_backend_reply_before_releasing(self):
        import threading
        started, finish = threading.Event(), threading.Event()
        original = Lease.acquire

        def delayed(lease):
            if lease.name == 'ws_connections':
                started.set()
                if not finish.wait(5): raise AssertionError('Acquisition test timed out')
            return original(lease)

        async def run():
            socket = self.socket()
            connection = asyncio.create_task(socket.connect(timeout=5))
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 3))
                socket.future.cancel()
                finish.set()
                await asyncio.gather(socket.future, return_exceptions=True)
            finally:
                finish.set(); connection.cancel()
                await asyncio.gather(connection, return_exceptions=True)
        with patch('config.socket_limits.Lease.acquire', delayed):
            async_to_sync(run)()
        held = []
        try:
            for _ in range(3): held.append(Lease('ws_connections', 1).acquire())
        finally:
            for lease in held: lease.release()

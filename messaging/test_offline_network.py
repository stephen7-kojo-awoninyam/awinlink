"""Exercise Windows asyncio socketpairs without allowing outbound test traffic."""
import socket
from asgiref.sync import async_to_sync
from django.test import SimpleTestCase
from scripts.audit_turn_ice_local import offline_network


class OfflineNetworkTests(SimpleTestCase):
    def test_socketpair_and_asyncio_work_while_outbound_connections_are_blocked(self):
        async def signal():
            return 'local-only'

        with offline_network():
            first, second = socket.socketpair()
            try:
                first.sendall(b'x')
                self.assertEqual(second.recv(1), b'x')
            finally:
                first.close()
                second.close()
            self.assertEqual(async_to_sync(signal)(), 'local-only')
            with socket.socket() as sock:
                for address in [('192.0.2.1', 3478), ('127.0.0.1', 3478)]:
                    with self.assertRaisesRegex(RuntimeError, 'Network access is disabled'):
                        sock.connect(address)
                with self.assertRaises(RuntimeError):
                    sock.connect_ex(('192.0.2.1', 3478))
                with self.assertRaises(RuntimeError):
                    sock.sendto(b'x', ('192.0.2.1', 3478))
            with self.assertRaises(RuntimeError):
                socket.getaddrinfo('relay.invalid', 3478)

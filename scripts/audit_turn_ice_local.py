"""Offline TURN/ICE audit checks; no dotenv, database, relay or deployment access.

Run from the repository root: .venv/Scripts/python.exe -B scripts/audit_turn_ice_local.py
"""
import os
from pathlib import Path
import socket
import sys
import threading
import ipaddress
from contextlib import contextmanager
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def deny_network(*args, **kwargs):
    raise RuntimeError("Network access is disabled for this audit")


@contextmanager
def offline_network():
    """Allow only socketpair's own loopback connect for Windows asyncio wakeups."""
    local = threading.local()
    original_pair = socket.socketpair
    original_connect = socket.socket.connect

    def socketpair(*args, **kwargs):
        local.creating_pair = True
        try:
            return original_pair(*args, **kwargs)
        finally:
            local.creating_pair = False

    def connect(sock, address):
        if getattr(local, 'creating_pair', False) and isinstance(address, tuple) and ipaddress.ip_address(address[0]).is_loopback:
            return original_connect(sock, address)
        return deny_network()

    with patch.object(socket, 'socketpair', socketpair), \
            patch.object(socket.socket, 'connect', connect), \
            patch.object(socket.socket, 'connect_ex', deny_network), \
            patch.object(socket.socket, 'sendto', deny_network), \
            patch.object(socket, 'getaddrinfo', deny_network):
        yield


if __name__ == "__main__":
    # Do not load local secrets or inherit hosted service configuration.
    with patch.dict(os.environ, {
        "DJANGO_SETTINGS_MODULE": "config.settings",
        "AWINLINK_ENV": "development", "DEBUG": "true",
        "SECRET_KEY": "offline-audit-only-not-a-production-secret",
    }, clear=True), patch("dotenv.load_dotenv", return_value=False), offline_network():
        import django
        django.setup()
        from django.conf import settings
        from django.core.management import call_command
        from django.core.management.base import CommandError
        from django.test.runner import DiscoverRunner

        settings.DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
        settings.CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
        settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
        # Avoid scanning collected static trees during origin middleware tests.
        settings.MIDDLEWARE = [item for item in settings.MIDDLEWARE if not item.startswith('whitenoise.')]
        print("Repository defaults with dotenv disabled (not deployed configuration):", flush=True)
        try:
            call_command("check_turn")
        except CommandError:
            print("Expected: default TURN configuration is incomplete.", flush=True)
        failures = DiscoverRunner(verbosity=2).run_tests([
            "messaging.test_call_media",
            "messaging.test_offline_network",
            "messaging.test_signaling_security.SignalingPayloadTests",
            "messaging.test_signaling_security.WebSocketOriginTests",
            "learning.test_classroom_signaling.ClassroomSignalValidationTests",
        ])
        sys.exit(bool(failures))

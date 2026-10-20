"""Restrict server-side Web Push delivery to browser vendor services."""
import ipaddress
import socket
from urllib.parse import urlsplit

import requests

EXACT_HOSTS = frozenset({'fcm.googleapis.com', 'updates.push.services.mozilla.com', 'web.push.apple.com'})


def validate_push_endpoint(value, *, resolve=False):
    if not isinstance(value, str) or len(value) > 2048 or any(c.isspace() or ord(c) < 32 for c in value):
        raise ValueError('Invalid push endpoint.')
    try:
        url = urlsplit(value)
        host = url.hostname or ''
        allowed = host in EXACT_HOSTS or (host.endswith('.notify.windows.com') and host != '.notify.windows.com')
        if not allowed or url.scheme != 'https' or url.port not in (None, 443) or url.username or url.password or url.fragment or not url.path or '\\' in value:
            raise ValueError('Unsupported push endpoint.')
        if resolve:
            addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
                raise ValueError('Push destination must be public.')
    except (ValueError, OSError):
        raise ValueError('Unsupported push endpoint.') from None
    return value


class SafePushSession(requests.Session):
    def __init__(self):
        super().__init__()
        # Ignore proxy environment variables that could bypass destination checks.
        self.trust_env = False

    def post(self, url, **kwargs):
        validate_push_endpoint(url, resolve=True)
        kwargs['allow_redirects'] = False
        kwargs['timeout'] = (3, 5)
        kwargs['verify'] = True
        return super().post(url, **kwargs)

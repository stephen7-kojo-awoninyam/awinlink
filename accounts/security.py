"""Shared web/API authentication limits; keys never contain raw identities or IPs."""
import time
from unicodedata import normalize

from django.conf import settings
from django.core.cache import caches
from django.core.cache.backends.locmem import LocMemCache
from django.core.cache.backends.dummy import DummyCache
from django.utils.crypto import salted_hmac
from rest_framework.exceptions import APIException, Throttled
from rest_framework.throttling import BaseThrottle

from .recovery import client_address


class AuthenticationUnavailable(APIException):
    status_code = 503
    default_detail = 'Authentication protection is temporarily unavailable. Please try again later.'


def enforce_auth_limit(request, scope, identifier='', *, dimensions=None):
    policy = settings.AUTH_RATE_LIMITS[scope]
    values = {'ip': client_address(request)}
    if isinstance(identifier, str) and identifier.strip():
        values['identity'] = normalize('NFKC', identifier.strip()).casefold()[:256]
    elif getattr(request.user, 'is_authenticated', False):
        values['identity'] = 'user:' + str(request.user.pk)
    try:
        cache = caches[settings.AUTH_RATE_LIMIT_CACHE_ALIAS]
        if settings.AUTH_RATE_LIMIT_REQUIRE_SHARED_CACHE and isinstance(cache, (LocMemCache, DummyCache)):
            raise AuthenticationUnavailable()
        for dimension, (limit, seconds) in policy.items():
            if dimension not in values or (dimensions is not None and dimension not in dimensions):
                continue
            digest = salted_hmac('auth-limit:' + scope + ':' + dimension, values[dimension]).hexdigest()
            key = f'auth:{scope}:{dimension}:{int(time.time()) // seconds}:{digest}'
            if cache.add(key, 1, timeout=seconds + 1):
                continue
            try:
                permitted = cache.incr(key) <= limit
            except ValueError:
                permitted = bool(cache.add(key, 1, timeout=seconds + 1))
            if not permitted:
                raise Throttled(wait=seconds, detail='Too many attempts. Please try again later.')
    except (Throttled, AuthenticationUnavailable):
        raise
    except Exception:
        # Cache exception text can contain Redis URLs, so never log or expose it.
        raise AuthenticationUnavailable() from None


class AuthenticationThrottle(BaseThrottle):
    scope = 'login'

    def allow_request(self, request, view):
        # Consume the IP budget before JSON parsing, including malformed bodies.
        enforce_auth_limit(request, self.scope, dimensions=('ip',))
        identifier = ''
        if self.scope in {'login', 'registration'}:
            data = request.data
            if hasattr(data, 'get'):
                identifier = data.get('username', '')
        enforce_auth_limit(request, self.scope, identifier, dimensions=('identity',))
        return True


class RegistrationThrottle(AuthenticationThrottle):
    scope = 'registration'


class RefreshThrottle(AuthenticationThrottle):
    scope = 'refresh'


class GoogleThrottle(AuthenticationThrottle):
    scope = 'google'


class PushThrottle(AuthenticationThrottle):
    scope = 'push'

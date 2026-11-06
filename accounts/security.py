"""Shared web/API authentication limits; keys never contain raw identities or IPs."""
import time
from unicodedata import normalize

from django.conf import settings
from django.core.cache import caches
from django.core.cache.backends.redis import RedisCache
from django.core.cache.backends.memcached import BaseMemcachedCache
from django.utils.crypto import salted_hmac
from rest_framework.exceptions import APIException, Throttled
from rest_framework.throttling import BaseThrottle

from .recovery import client_address


class AuthenticationUnavailable(APIException):
    status_code = 503
    default_detail = 'Authentication protection is temporarily unavailable. Please try again later.'


def is_shared_auth_cache(cache):
    # File/database caches and arbitrary cache backends do not guarantee atomic
    # counters across workers. These supported backends provide add/incr semantics.
    return isinstance(cache, (RedisCache, BaseMemcachedCache))


def enforce_auth_limit(request, scope, identifier='', *, dimensions=None):
    values = {'ip': client_address(request)}
    if isinstance(identifier, str) and identifier.strip():
        values['identity'] = normalize('NFKC', identifier.strip()[:256]).casefold()[:256]
    elif getattr(request.user, 'is_authenticated', False):
        values['identity'] = 'user:' + str(request.user.pk)
    try:
        policy = settings.AUTH_RATE_LIMITS[scope]
        if not policy or any(dimension not in ('ip', 'identity') or len(budget) != 2 or
                any(type(value) is not int or value <= 0 for value in budget)
                for dimension, budget in policy.items()):
            raise AuthenticationUnavailable()
        cache = caches[settings.AUTH_RATE_LIMIT_CACHE_ALIAS]
        if settings.AUTH_RATE_LIMIT_REQUIRE_SHARED_CACHE and not is_shared_auth_cache(cache):
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


class SafetyReportThrottle(AuthenticationThrottle):
    scope = 'safety_report'

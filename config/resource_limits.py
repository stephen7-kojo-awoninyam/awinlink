"""Atomic, expiring resource budgets. Redis is mandatory outside development.

All keys use the configured security cache namespace. Lua uses Redis time, so
workers cannot reset budgets through clock skew or a read/modify/write race.
"""
import math
import threading
import time
from uuid import uuid4

from django.conf import settings
from django.core.cache import caches
from django.core.cache.backends.locmem import LocMemCache
from django.core.cache.backends.redis import RedisCache
from django.utils.crypto import salted_hmac
from rest_framework.exceptions import APIException, Throttled


class ResourceUnavailable(APIException):
    status_code = 503
    default_detail = 'Resource protection is temporarily unavailable. Please try again later.'


class ResourceLimited(Throttled):
    default_detail = 'Resource limit reached. Please try again later.'


# A bucket's TTL covers the time to refill completely, including large uploads.
BUCKET = """
local t = redis.call('TIME'); local now = tonumber(t[1]) + tonumber(t[2])/1000000
local capacity, period, cost = tonumber(ARGV[1]), tonumber(ARGV[2]), tonumber(ARGV[3])
local state = redis.call('HMGET', KEYS[1], 'tokens', 'time')
local tokens = math.min(capacity, tonumber(state[1] or capacity) + math.max(0, now-tonumber(state[2] or now))*capacity/period)
if tokens < cost then return math.ceil((cost-tokens)*period/capacity) end
redis.call('HSET', KEYS[1], 'tokens', tokens-cost, 'time', now)
redis.call('EXPIRE', KEYS[1], math.ceil(period)+1)
return 0
"""
LEASE = """
local t = redis.call('TIME'); local now = tonumber(t[1]) + tonumber(t[2])/1000000
local limit, ttl, token, action = tonumber(ARGV[1]), tonumber(ARGV[2]), ARGV[3], ARGV[4]
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
if action == 'release' then redis.call('ZREM', KEYS[1], token); return 1 end
local exists = redis.call('ZSCORE', KEYS[1], token)
if action == 'renew' and not exists then return 0 end
if not exists and redis.call('ZCARD', KEYS[1]) >= limit then return 0 end
redis.call('ZADD', KEYS[1], now+ttl, token)
redis.call('EXPIRE', KEYS[1], math.ceil(ttl)+1)
return 1
"""
_local_lock = threading.RLock()


def policy(name):
    try:
        values = settings.AWINLINK_RESOURCE_LIMITS[name]
        if len(values) != 2 or any(type(v) is not int or v <= 0 for v in values):
            raise ValueError()
        return values
    except Exception:
        raise ResourceUnavailable() from None


def _backend(name, identity):
    cache = caches[getattr(settings, 'AWINLINK_RESOURCE_CACHE_ALIAS', 'security')]
    key = cache.make_key('resource:v1:' + name + ':' + salted_hmac('resource:' + name, str(identity)).hexdigest())
    if isinstance(cache, RedisCache):
        return cache, key, cache._cache.get_client(key, write=True)
    # Only the built-in local cache is supported for explicitly local development.
    if settings.AWINLINK_ENV == 'development' and not settings.HOSTED_PRODUCTION and isinstance(cache, LocMemCache):
        return cache, key, None
    raise ResourceUnavailable()


def consume(name, identity, cost=1):
    capacity, period = policy(name)
    if type(cost) is not int or cost <= 0:
        raise ResourceUnavailable()
    if cost > capacity:
        raise ResourceLimited(wait=period)
    try:
        cache, key, client = _backend(name, identity)
        if client is not None:
            wait = int(client.eval(BUCKET, 1, key, capacity, period, cost))
        else:
            with _local_lock:
                now = time.monotonic()
                tokens, previous = cache.get(key, (capacity, now))
                tokens = min(capacity, tokens + max(0, now-previous)*capacity/period)
                wait = math.ceil((cost-tokens)*period/capacity) if tokens < cost else 0
                if not wait:
                    cache.set(key, (tokens-cost, now), timeout=period+1)
        if wait:
            raise ResourceLimited(wait=wait)
    except (ResourceLimited, ResourceUnavailable):
        raise
    except Exception:
        # Connection errors may contain credentials. Never expose their text.
        raise ResourceUnavailable() from None


class Lease:
    def __init__(self, name, identity):
        self.name, self.identity, self.token = name, identity, uuid4().hex
        self.limit, self.ttl = policy(name)

    def _update(self, action):
        try:
            cache, key, client = _backend(self.name, self.identity)
            if client is not None:
                return bool(client.eval(LEASE, 1, key, self.limit, self.ttl, self.token, action))
            with _local_lock:
                now = time.monotonic()
                leases = {k: v for k, v in cache.get(key, {}).items() if v > now}
                if action == 'release':
                    leases.pop(self.token, None)
                elif action == 'renew' and self.token not in leases:
                    return False
                elif self.token not in leases and len(leases) >= self.limit:
                    return False
                else:
                    leases[self.token] = now + self.ttl
                cache.set(key, leases, timeout=self.ttl+1)
                return True
        except ResourceUnavailable:
            raise
        except Exception:
            raise ResourceUnavailable() from None

    def acquire(self):
        if not self._update('acquire'):
            raise ResourceLimited(wait=self.ttl)
        return self

    def renew(self):
        if not self._update('renew'):
            raise ResourceLimited(wait=self.ttl)

    def release(self):
        self._update('release')

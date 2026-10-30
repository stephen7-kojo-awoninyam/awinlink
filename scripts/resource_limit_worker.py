"""Independent worker for the disposable Redis resource-limit fixture only."""
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
url = os.environ.get('AWINLINK_SECURITY_TEST_REDIS_URL', '')
prefix = os.environ.get('AWINLINK_SECURITY_TEST_PREFIX', '')
parsed = urlsplit(url)
if parsed.scheme != 'redis' or parsed.hostname != '127.0.0.1' or not parsed.port or not parsed.password or not prefix.startswith('awinlink-admin-test-'):
    raise RuntimeError('Only the isolated loopback Redis fixture is allowed.')
for name in tuple(os.environ):
    if name.startswith(('RAILWAY_', 'RENDER')): os.environ.pop(name)
os.environ.update(AWINLINK_ENV='development', DEBUG='true', DJANGO_SETTINGS_MODULE='config.settings',
    DATABASE_URL='sqlite:///:memory:', REDIS_URL='', SECRET_KEY='fixture-only-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ-abcdefgh')

import django
from django.conf import settings
with patch('dotenv.load_dotenv'):
    settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
    settings.CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
        'resource_fixture': {'BACKEND': 'django.core.cache.backends.redis.RedisCache', 'LOCATION': url,
                            'KEY_PREFIX': prefix, 'OPTIONS': {'socket_timeout': 2, 'socket_connect_timeout': 2}}}
    settings.AWINLINK_RESOURCE_CACHE_ALIAS = 'resource_fixture'
    settings.AWINLINK_RESOURCE_LIMITS = {'race_bytes': (30, 3600), 'race_slots': (3, 20)}
    django.setup()

import redis
from redis.backoff import NoBackoff
from redis.retry import Retry
from config.resource_limits import Lease, ResourceLimited, consume

mode, run = sys.argv[1:3]
barrier = redis.Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2, retry=Retry(NoBackoff(), 0))

def rendezvous(stage):
    key = prefix + ':resource:' + run + ':' + stage
    barrier.incr(key); barrier.expire(key, 90)
    deadline = time.monotonic() + 40
    while int(barrier.get(key) or 0) < 2:
        if time.monotonic() >= deadline: raise RuntimeError('Fixture worker barrier timed out.')
        time.sleep(.01)

leases, allowed, limited = [], 0, 0
try:
    rendezvous('start')
    for _ in range(10):
        try:
            if mode == 'bytes': consume('race_bytes', run, 10)
            else: leases.append(Lease('race_slots', run).acquire())
            allowed += 1
        except ResourceLimited: limited += 1
    rendezvous('finish')  # Hold all leases until both workers have attempted.
finally:
    for lease in leases: lease.release()
    barrier.close()
print(json.dumps({'allowed': allowed, 'limited': limited}))

"""One isolated in-process HTTP worker for the Redis admin-login regression."""
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
    if name.startswith(('RAILWAY_', 'RENDER')):
        os.environ.pop(name)
os.environ.update(AWINLINK_ENV='development', DEBUG='true', DJANGO_SETTINGS_MODULE='config.settings',
    DATABASE_URL='sqlite:///:memory:', REDIS_URL='', SECRET_KEY='fixture-only-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ-abcdefgh')

import django
from django.conf import settings
with patch('dotenv.load_dotenv'):
    settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
    settings.CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
        'admin_fixture': {'BACKEND': 'django.core.cache.backends.redis.RedisCache', 'LOCATION': url,
                          'KEY_PREFIX': prefix, 'OPTIONS': {'socket_timeout': 2, 'socket_connect_timeout': 2}}}
    settings.AUTH_RATE_LIMIT_CACHE_ALIAS = 'admin_fixture'
    settings.AUTH_RATE_LIMIT_REQUIRE_SHARED_CACHE = True
    settings.AUTH_RATE_LIMITS = {'login': {'ip': (100, 600), 'identity': (3, 600)}}
    settings.PASSWORD_RESET_TRUSTED_IP_HEADER = ''
    settings.PASSWORD_RESET_TRUSTED_PROXY_COUNT = 0
    settings.ALLOWED_HOSTS = ['testserver']
    settings.STORAGES = {'default': {'BACKEND': 'django.core.files.storage.InMemoryStorage'},
                        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}
    django.setup()

from django.test import Client
from django.urls import reverse
browser = Client(enforce_csrf_checks=True)
browser.get(reverse('admin:login'))
username = 'PARALLEL-ADMIN' if sys.argv[1] == '0' else 'ｐａｒａｌｌｅｌ－ａｄｍｉｎ'
# Both processes finish Django startup before racing the shared attempt budget.
import redis
from redis.backoff import NoBackoff
from redis.retry import Retry
barrier = redis.Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2, retry=Retry(NoBackoff(), 0))
try:
    key = prefix + ':ready'
    barrier.incr(key); barrier.expire(key, 60)
    deadline = time.monotonic() + 30
    while int(barrier.get(key) or 0) < 2:
        if time.monotonic() >= deadline:
            raise RuntimeError('The second isolated worker did not reach the fixture barrier.')
        time.sleep(.01)
finally:
    barrier.close()
with patch('accounts.security.time.time', return_value=float(os.environ['AWINLINK_SECURITY_TEST_FIXED_TIME'])), \
        patch('django.contrib.auth.forms.authenticate', return_value=None) as authenticate:
    statuses = [browser.post(reverse('admin:login'), {'username': username, 'password': 'invalid-fixture-password',
        'csrfmiddlewaretoken': browser.cookies['csrftoken'].value}).status_code for _ in range(5)]
print(json.dumps({'statuses': statuses, 'password_checks': authenticate.call_count}))

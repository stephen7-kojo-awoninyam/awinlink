"""Run Django audits only against isolated SQLite or explicit loopback test services."""
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
os.environ["DATABASE_URL"] = ""
os.environ["REDIS_URL"] = ""
from django.conf import settings

settings.DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
postgres = os.environ.get("AWINLINK_AUDIT_POSTGRES_URL")
if postgres:
    import dj_database_url
    parsed = urlparse(postgres)
    name = unquote(parsed.path.lstrip("/"))
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or not name.startswith("awinlink_audit_"):
        raise SystemExit("Refusing non-loopback/non-audit PostgreSQL")
    database = dj_database_url.parse(postgres)
    database["TEST"] = {"NAME": "test_" + name}
    settings.DATABASES = {"default": database}
settings.CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
redis = os.environ.get("VC_AUDIT_REDIS_URL")
if redis:
    parsed = urlparse(redis)
    if parsed.scheme not in {"redis", "rediss"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("Refusing non-loopback audit Redis")
    settings.CHANNEL_LAYERS = {"default": {"BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [redis], "prefix": "vc-audit-" + uuid4().hex}}}
    os.environ["CLASSROOM_TEST_REDIS_URL"] = redis
settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
settings.STORAGES = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                     "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}
settings.MEDIA_ROOT = ROOT / ".audit-vc-media"
settings.WEB_PUSH_PUBLIC_KEY = settings.WEB_PUSH_PRIVATE_KEY = settings.EXPO_PUSH_ACCESS_TOKEN = ""
from django.core.management import execute_from_command_line
execute_from_command_line(["manage.py", *sys.argv[1:]])

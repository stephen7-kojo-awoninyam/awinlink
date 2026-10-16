"""Run audit commands against isolated local resources, never the configured DB."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if os.environ.get('AWINLINK_AUDIT_LOG'):
    audit_log = ROOT / Path(os.environ['AWINLINK_AUDIT_LOG']).name
    sys.stdout = sys.stderr = audit_log.open('w', encoding='utf-8', buffering=1)
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
os.environ['DATABASE_URL'] = ''
os.environ['REDIS_URL'] = ''
os.environ['EXPO_PUSH_ACCESS_TOKEN'] = ''
from django.conf import settings

settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
if os.environ.get('AWINLINK_AUDIT_POSTGRES_URL'):
    from urllib.parse import unquote, urlparse
    import dj_database_url
    audit_database_url = os.environ['AWINLINK_AUDIT_POSTGRES_URL']
    parsed = urlparse(audit_database_url)
    audit_database_name = unquote(parsed.path.lstrip('/'))
    if parsed.scheme not in ('postgres', 'postgresql') or parsed.hostname not in ('localhost', '127.0.0.1', '::1') or not audit_database_name.startswith('awinlink_audit_'):
        raise SystemExit('Audit PostgreSQL must be loopback-only with an awinlink_audit_ database name.')
    database = dj_database_url.parse(audit_database_url)
    database['TEST'] = {'NAME': 'test_' + audit_database_name}
    settings.DATABASES = {'default': database}
settings.CHANNEL_LAYERS = {'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}
settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
settings.STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}
settings.MEDIA_ROOT = ROOT / '.audit-media'
settings.EXPO_PUSH_ACCESS_TOKEN = ''
if os.environ.get('AWINLINK_AUDIT_FAST_TESTS') == '1' and sys.argv[1:2] == ['test']:
    settings.PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
settings.WEB_PUSH_PRIVATE_KEY = ''
settings.WEB_PUSH_PUBLIC_KEY = ''
if len(sys.argv) > 1 and sys.argv[1] == 'collectstatic':
    settings.STATIC_ROOT = ROOT / '.audit-static'
    settings.STORAGES['staticfiles'] = {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'
    }
from django.core.management import execute_from_command_line
execute_from_command_line(['manage.py', *sys.argv[1:]])

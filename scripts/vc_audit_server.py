"""Two loopback ASGI workers and synthetic fixtures for real browser RTC auditing."""
import argparse
from datetime import timedelta
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / '.audit-vc-e2e'
sys.path.insert(0, str(ROOT))
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
os.environ['DATABASE_URL'] = ''
os.environ['REDIS_URL'] = ''
from django.conf import settings
settings.SECRET_KEY = 'local-vc-audit-only-not-a-release-secret'
settings.DEBUG = True
settings.ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'testserver']
settings.SECURE_SSL_REDIRECT = False
settings.SESSION_COOKIE_SECURE = settings.CSRF_COOKIE_SECURE = False
settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql', 'HOST': '127.0.0.1',
    'PORT': '55432', 'USER': 'vc_audit', 'PASSWORD': '', 'NAME': 'awinlink_audit_vc_e2e'}}
settings.STORAGES = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                     'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}
settings.MEDIA_ROOT = ARTIFACTS / 'media'
settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
settings.WEB_PUSH_PUBLIC_KEY = settings.WEB_PUSH_PRIVATE_KEY = settings.EXPO_PUSH_ACCESS_TOKEN = ''
settings.TURN_SERVER_URLS = settings.TURN_SHARED_SECRET = ''
settings.PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
manifest_path = ARTIFACTS / 'fixture.json'
if manifest_path.exists():
    prefix = json.loads(manifest_path.read_text())['redis_prefix']
else:
    prefix = 'vc-e2e-' + uuid4().hex
settings.CHANNEL_LAYERS = {'default': {'BACKEND': 'channels_redis.core.RedisChannelLayer',
    'CONFIG': {'hosts': ['redis://127.0.0.1:16379/0'], 'prefix': prefix}}}


def prepare():
    import psycopg2
    connection = psycopg2.connect(host='127.0.0.1', port=55432, user='vc_audit', dbname='postgres')
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_database WHERE datname='awinlink_audit_vc_e2e'")
        if cursor.fetchone() is None: cursor.execute('CREATE DATABASE awinlink_audit_vc_e2e')
    connection.close()
    import django
    django.setup()
    from django.core.management import call_command
    call_command('migrate', interactive=False, verbosity=0)
    from django.contrib.auth import get_user_model, SESSION_KEY, BACKEND_SESSION_KEY, HASH_SESSION_KEY
    from django.contrib.sessions.backends.db import SessionStore
    from django.utils import timezone
    from learning.models import LearningCategory, Course, Lesson, Enrollment
    from learning import classroom_services as services
    nonce = uuid4().hex[:8]
    users = {kind: get_user_model().objects.create_user(username=f'vc-audit-{nonce}-{kind}',
        role='COACH' if kind == 'host' else 'ATHLETE') for kind in ['host', 'learner', 'waiting', 'outsider']}
    host = users['host']
    category = LearningCategory.objects.create(name='VC audit ' + nonce)
    course = Course.objects.create(creator=host, category=category, title='VC audit course', slug='vc-audit-' + nonce,
        description='Synthetic audit fixtures only', status='APPROVED')
    lesson = Lesson.objects.create(course=course, title='VC audit lesson', order=1)
    for kind in ['learner', 'waiting']: Enrollment.objects.create(user=users[kind], course=course)
    room = services.create_classroom(actor=host, course=course, title='VC audit classroom', capacity=10)
    starts = timezone.now() + timedelta(minutes=1)
    session = services.schedule_session(actor=host, classroom=room, lesson=lesson, title='VC audit live session',
        scheduled_start=starts, scheduled_end=starts + timedelta(hours=1))
    services.start_session(actor=host, session=session)
    learner = services.request_admission(actor=users['learner'], session=session)
    services.admit_participant(actor=host, session=session, participant=learner)
    waiting = services.request_admission(actor=users['waiting'], session=session)
    other_room = services.create_classroom(actor=host, course=course, title='Isolated audit room')
    other_session = services.schedule_session(actor=host, classroom=other_room, lesson=lesson, title='Other audit session',
        scheduled_start=starts, scheduled_end=starts + timedelta(hours=1))
    services.start_session(actor=host, session=other_session)
    identities = {}
    for kind, user in users.items():
        store = SessionStore()
        store[SESSION_KEY] = str(user.pk)
        store[BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
        store[HASH_SESSION_KEY] = user.get_session_auth_hash()
        store.save()
        identities[kind] = {'user_id': user.pk, 'username': user.username, 'session_cookie': store.session_key}
    ARTIFACTS.mkdir(exist_ok=True)
    fixture = {'session_id': session.pk, 'other_session_id': other_session.pk, 'room_id': room.pk,
        'learner_participant_id': learner.pk, 'waiting_participant_id': waiting.pk,
        'cookie_name': settings.SESSION_COOKIE_NAME, 'identities': identities, 'redis_prefix': prefix}
    manifest_path.write_text(json.dumps(fixture, indent=2))
    # No session credentials in stdout or public evidence.
    print(json.dumps({'fixture_ready': True, 'session_id': session.pk, 'database': 'awinlink_audit_vc_e2e'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--port', type=int, choices=[18765, 18766])
    args = parser.parse_args()
    if args.prepare: prepare()
    else:
        import django
        django.setup()
        from config.asgi import application
        from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
        from daphne.server import Server
        Server(ASGIStaticFilesHandler(application), endpoints=[f'tcp:port={args.port}:interface=127.0.0.1'],
            signal_handlers=True).run()

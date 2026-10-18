"""Seeded upgrade probes, exclusively in disposable local PostgreSQL databases.

Run with the repository virtualenv. This never reads DATABASE_URL, changes a
deployment, or modifies the existing audit databases.
"""
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

import psycopg2
from psycopg2 import sql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['DATABASE_URL'] = ''
os.environ['REDIS_URL'] = ''
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
from django.conf import settings

settings.DATABASES = {'default': {
    'ENGINE': 'django.db.backends.postgresql', 'HOST': '127.0.0.1',
    'PORT': 55432, 'USER': 'vc_audit', 'NAME': 'unused',
}}
import django
django.setup()
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.autodetector import MigrationAutodetector
from django.db.migrations.state import ProjectState
from django.utils import timezone


def users(apps):
    User = apps.get_model('accounts', 'User')
    return [User.objects.create(username=name) for name in ['talent', 'sender']]


def market(apps, variant):
    talent, sender = users(apps)
    profile = apps.get_model('talents', 'TalentProfile').objects.create(user_id=talent.pk)
    domain = apps.get_model('domains', 'TalentDomain').objects.create(name='Basketball')
    listing = apps.get_model('marketplace', 'Listing').objects.create(
        talent_id=profile.pk, subecosystem_id=domain.pk, ecosystem='SPORTS',
        title='Player', description='Skills', status='PUBLISHED',
        publication_consented_at=None if variant == 'missing_consent' else timezone.now())
    Offer = apps.get_model('marketplace', 'Offer')
    data = {'listing_id': listing.pk, 'sender_id': sender.pk, 'terms': 'Terms'}
    if variant == 'duplicate_organization':
        org = apps.get_model('organizations', 'Organization').objects.create(name='Club', user_id=sender.pk)
        data['organization_id'] = org.pk
    Offer.objects.create(**data)
    if variant.startswith('duplicate'):
        Offer.objects.create(**data)
    return lambda current: {
        'listings': current.get_model('marketplace', 'Listing').objects.count(),
        'offers': current.get_model('marketplace', 'Offer').objects.count(),
    }


def conversation(apps):
    talent, sender = users(apps)
    profile = apps.get_model('talents', 'TalentProfile').objects.create(user_id=talent.pk)
    org = apps.get_model('organizations', 'Organization').objects.create(name='Club', user_id=sender.pk)
    room = apps.get_model('messaging', 'Conversation').objects.create(talent_id=profile.pk, organization_id=org.pk)
    apps.get_model('messaging', 'Message').objects.create(conversation_id=room.pk, sender_id=sender.pk, content='Preserved message')
    def verify(current):
        participants = list(current.get_model('messaging', 'ConversationParticipant').objects.filter(conversation_id=room.pk).values_list('user_id', flat=True))
        return {'participants': participants, 'expected_participants': [talent.pk, sender.pk],
                'message_count': current.get_model('messaging', 'Message').objects.count(),
                'data_loss': set(participants) != {talent.pk, sender.pk}}
    return verify


def calls(apps):
    talent, sender = users(apps)
    room = apps.get_model('messaging', 'Conversation').objects.create()
    Call = apps.get_model('messaging', 'Call')
    for status in ['ACCEPTED', 'REJECTED', 'ENDED', 'RINGING']:
        Call.objects.create(conversation_id=room.pk, caller_id=sender.pk, receiver_id=talent.pk, status=status, call_type='VOICE')
    def verify(current):
        rows = list(current.get_model('messaging', 'Call').objects.values_list('status', flat=True))
        return {'statuses': rows, 'invalid_statuses': [s for s in rows if s not in ['ACTIVE', 'ENDED', 'MISSED', 'RINGING']],
                'participants': current.get_model('messaging', 'CallParticipant').objects.count()}
    return verify


def read_history(apps):
    talent, sender = users(apps)
    room = apps.get_model('messaging', 'Conversation').objects.create()
    apps.get_model('messaging', 'ConversationParticipant').objects.create(conversation_id=room.pk, user_id=talent.pk)
    message = apps.get_model('messaging', 'Message').objects.create(conversation_id=room.pk, sender_id=sender.pk, content='Read', is_read=True)
    def verify(current):
        row = current.get_model('messaging', 'ConversationParticipant').objects.get(conversation_id=room.pk, user_id=talent.pk)
        return {'read_history_preserved': row.last_read_at == message.created_at}
    return verify


def main():
    admin = psycopg2.connect(host='127.0.0.1', port=55432, user='vc_audit', dbname='postgres', connect_timeout=3)
    admin.autocommit = True
    with admin.cursor() as cursor:
        cursor.execute('SHOW data_directory')
        if Path(cursor.fetchone()[0]).resolve() != (ROOT / '.audit-vc-tools/postgres-data').resolve():
            raise RuntimeError('Refusing a PostgreSQL cluster outside the workspace audit directory')
        cursor.execute('SHOW server_version')
        version = cursor.fetchone()[0]
    probes = [
        ('market_clean', ('marketplace', '0001_initial'), ('marketplace', '0002_workflow_guards'), lambda apps: market(apps, 'clean')),
        *[(f'market_{variant}', ('marketplace', '0001_initial'), ('marketplace', '0002_workflow_guards'), lambda apps, v=variant: market(apps, v))
          for variant in ['duplicate_personal', 'duplicate_organization', 'missing_consent']],
        ('messaging_participants', ('messaging', '0005_message_video'), ('messaging', '0006_alter_conversation_unique_together_and_more'), conversation),
        ('messaging_calls', ('messaging', '0009_conversation_created_by_conversation_image_and_more'), ('messaging', '0010_remove_call_caller_remove_call_receiver_and_more'), calls),
        ('messaging_read_history', ('messaging', '0011_message_reply_to'), ('messaging', '0012_conversationparticipant_last_read_at'), read_history),
    ]
    results = []
    for label, before, after, seed in probes:
        name = 'awinlink_audit_tm_' + uuid4().hex
        with admin.cursor() as cursor:
            cursor.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        result = {'probe': label}
        try:
            connection.close()
            connection.settings_dict['NAME'] = name
            executor = MigrationExecutor(connection)
            executor.migrate([before])
            verify = seed(executor.loader.project_state([before]).apps)
            executor = MigrationExecutor(connection)
            executor.migrate([after])
            result['migration'] = 'passed'
            result['verification'] = verify(executor.loader.project_state([after]).apps)
            if label == 'market_clean':
                executor = MigrationExecutor(connection)
                changes = MigrationAutodetector(executor.loader.project_state(), ProjectState.from_apps(django.apps.apps)).changes(graph=executor.loader.graph)
                result['model_migration_drift'] = sorted(set(changes) & {'marketplace', 'messaging'})
        except Exception as error:
            result.update(migration='failed', error_type=type(error).__name__, error=str(error))
        finally:
            connection.close()
            with admin.cursor() as cursor:
                cursor.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))
        results.append(result)
        print(json.dumps(result), flush=True)
    admin.close()
    report = {'postgresql': version, 'scope': 'Disposable workspace cluster only; no deployed data inspected', 'probes': results}
    (ROOT / 'audit-talent-market-postgresql.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()

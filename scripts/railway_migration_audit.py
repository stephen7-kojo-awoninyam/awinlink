"""Read-only production preflight. Never imports Django or runs migrations.

Credentials are captured from Railway in memory, never logged or written.
Only status/variable reads are allowed through the Railway wrapper. Database
queries run in a read-only repeatable-read transaction, always rolled back.
"""
import argparse
import base64
from datetime import datetime, timezone
import inspect
import json
import os
from pathlib import Path
import subprocess
import time
import zlib
from urllib.parse import urlparse

import psycopg2
from psycopg2.extras import RealDictCursor

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'f06cfe28-197d-4ddc-8311-420d81ef6de4'
ENVIRONMENT = '75812236-0bee-426b-bef3-bab0811f7941'
SERVICE = 'a80a9307-b793-4089-9d1e-59d87bb046b0'
APP_SERVICE = 'a084500a-adfc-49b6-96e3-3d3521595b6e'


def railway_json(command):
    if command not in ('status', 'database_variables', 'app_variables'):
        raise ValueError('Only Railway reads are allowed')
    args = ['railway.cmd', 'status', '--json'] if command == 'status' else [
        'railway.cmd', 'variable', 'list', '--project', PROJECT,
        '--environment', ENVIRONMENT, '--service',
        SERVICE if command == 'database_variables' else APP_SERVICE, '--json']
    result = subprocess.run(args, capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise RuntimeError(f'Railway {command} failed; output withheld to protect credentials')
    return json.loads(result.stdout)


def production_dsn(require_public=True):
    status = railway_json('status')
    if status['id'] != PROJECT:
        raise RuntimeError('Linked Railway project does not match the audited project')
    environment = next((e['node'] for e in status['environments']['edges']
                        if e['node']['id'] == ENVIRONMENT), None)
    if environment is None or environment['name'] != 'production':
        raise RuntimeError('Production environment identity could not be verified')
    services = {e['node']['serviceId']: e['node']['serviceName']
                for e in environment['serviceInstances']['edges']}
    if services.get(SERVICE) != 'Postgres' or services.get(APP_SERVICE) != 'awinlink':
        raise RuntimeError('Expected production services not found')
    variables = railway_json('database_variables')
    app_variables = railway_json('app_variables')
    internal = variables.get('DATABASE_URL')
    app_dsn = app_variables.get('DATABASE_URL')
    if not internal or not app_dsn:
        raise RuntimeError('Cannot verify the application database reference')
    # Never print either URL. Check the resolved target, including authentication.
    def identity(value):
        parsed = urlparse(value)
        return parsed.hostname, parsed.port or 5432, parsed.path, parsed.username, parsed.password
    if identity(internal) != identity(app_dsn):
        raise RuntimeError('Application DATABASE_URL differs from this Postgres service; refusing to guess')
    if not require_public:
        return None
    public = variables.get('DATABASE_PUBLIC_URL')
    parsed = urlparse(public or '')
    if parsed.scheme not in ('postgres', 'postgresql') or not parsed.hostname:
        raise RuntimeError('No existing public database endpoint; no network changes will be made')
    if parsed.hostname.endswith('.internal') or parsed.hostname in ('localhost', '127.0.0.1'):
        raise RuntimeError('Expected an existing external Railway database endpoint')
    if (parsed.path, parsed.username, parsed.password) != identity(internal)[2:]:
        raise RuntimeError('Public and private database identities differ')
    return public


class Reader:
    def __init__(self, connection, local_migrations=None):
        self.connection = connection
        self.started = time.monotonic()
        self.checks = {}
        self.columns = {}
        self.local_migrations = local_migrations

    def query(self, name, statement, params=()):
        if not statement.lstrip().upper().startswith(('SELECT ', 'WITH ')):
            raise ValueError('Only static SELECT queries are allowed')
        if time.monotonic() - self.started > 90:
            self.checks[name] = {'status': 'not_checked', 'reason': 'Total audit time budget reached'}
            return []
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('SAVEPOINT audit_check')
            try:
                cursor.execute(statement, params)
                rows = [dict(row) for row in cursor.fetchall()]
                self.checks[name] = {'status': 'checked', 'rows': rows}
                return rows
            except psycopg2.Error as error:
                cursor.execute('ROLLBACK TO SAVEPOINT audit_check')
                self.checks[name] = {'status': 'inconclusive', 'sqlstate': error.pgcode,
                                     'error_type': type(error).__name__}
                return []
            finally:
                cursor.execute('RELEASE SAVEPOINT audit_check')

    def has(self, table, *columns):
        return table in self.columns and set(columns).issubset(self.columns[table])

    def check(self, name, required, statement):
        missing = {table: sorted(set(cols) - self.columns.get(table, set()))
                   for table, cols in required.items() if not self.has(table, *cols)}
        if missing:
            self.checks[name] = {'status': 'not_applicable_to_schema', 'missing': missing}
            return []
        return self.query(name, statement)

    def run(self):
        self.query('transaction_safety', "SELECT current_database() AS database, current_user AS role, current_setting('server_version') AS postgres_version, current_setting('transaction_read_only') AS read_only, current_setting('transaction_isolation') AS isolation, current_setting('statement_timeout') AS statement_timeout, current_setting('lock_timeout') AS lock_timeout, CURRENT_TIMESTAMP AS snapshot_started")
        safety = self.checks['transaction_safety'].get('rows', [])
        if not safety or safety[0]['read_only'] != 'on' or safety[0]['isolation'] != 'repeatable read':
            raise RuntimeError('Read-only consistent snapshot was not established')
        rows = self.query('schema_columns', "SELECT c.relname AS table_name, a.attname AS column_name FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid WHERE n.nspname='public' AND c.relkind IN ('r','p') AND a.attnum>0 AND NOT a.attisdropped AND (c.relname LIKE 'marketplace_%' OR c.relname LIKE 'messaging_%' OR c.relname IN ('django_migrations','talents_talentprofile','organizations_organization')) ORDER BY c.relname,a.attnum")
        for row in rows:
            self.columns.setdefault(row['table_name'], set()).add(row['column_name'])
        migration_rows = self.check('migration_history', {'django_migrations': ['app', 'name', 'applied']}, "SELECT app,name,applied FROM public.django_migrations ORDER BY app,name")
        applied = {(row['app'], row['name']) for row in migration_rows}
        local = set(map(tuple, self.local_migrations)) if self.local_migrations is not None else {(path.parent.parent.name, path.stem) for path in ROOT.glob('*/migrations/[0-9]*.py')}
        self.checks['local_migration_comparison'] = {
            'status': 'checked' if self.checks['migration_history']['status'] == 'checked' else 'inconclusive',
            'pending_local': [f'{a}.{n}' for a, n in sorted(local - applied)],
            'unknown_to_checkout': [f'{a}.{n}' for a, n in sorted(applied - local)],
            'note': 'Filename comparison only; migration recorder does not prove physical schema or data integrity.'}
        self.query('constraints', "SELECT c.relname AS table_name, con.conname AS name, con.contype AS type, con.convalidated AS validated, pg_get_constraintdef(con.oid) AS definition FROM pg_catalog.pg_constraint con JOIN pg_catalog.pg_class c ON c.oid=con.conrelid JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND (c.relname LIKE 'marketplace_%' OR c.relname IN ('messaging_conversationparticipant','messaging_callparticipant')) ORDER BY c.relname,con.conname")
        self.query('indexes', "SELECT tab.relname AS table_name, idx.relname AS name, i.indisvalid AS valid, i.indisready AS ready, pg_get_indexdef(i.indexrelid) AS definition FROM pg_catalog.pg_index i JOIN pg_catalog.pg_class tab ON tab.oid=i.indrelid JOIN pg_catalog.pg_class idx ON idx.oid=i.indexrelid JOIN pg_catalog.pg_namespace n ON n.oid=tab.relnamespace WHERE n.nspname='public' AND (tab.relname LIKE 'marketplace_%' OR tab.relname IN ('messaging_conversationparticipant','messaging_callparticipant')) ORDER BY tab.relname,idx.relname")
        self.query('table_estimates', "SELECT relname AS table_name, n_live_tup AS estimated_rows FROM pg_catalog.pg_stat_user_tables WHERE schemaname='public' AND (relname LIKE 'marketplace_%' OR relname LIKE 'messaging_%') ORDER BY relname")
        listing = {'marketplace_listing': ['id', 'status', 'publication_consented_at']}
        self.check('listing_statuses', listing, "SELECT status,count(*) AS count FROM public.marketplace_listing GROUP BY status ORDER BY status")
        self.check('listing_consent', listing, "SELECT count(*) FILTER (WHERE status='PUBLISHED' AND publication_consented_at IS NULL) AS published_without_consent, count(*) FILTER (WHERE status NOT IN ('DRAFT','PUBLISHED','PAUSED')) AS invalid_status, count(*) FILTER (WHERE publication_consented_at>CURRENT_TIMESTAMP) AS future_consent FROM public.marketplace_listing")
        self.check('listing_consent_sample', listing, "SELECT id,status FROM public.marketplace_listing WHERE (status='PUBLISHED' AND publication_consented_at IS NULL) OR status NOT IN ('DRAFT','PUBLISHED','PAUSED') ORDER BY id LIMIT 20")
        offer = {'marketplace_offer': ['id', 'listing_id', 'sender_id', 'organization_id', 'status', 'decided_at', 'talent_consented_at']}
        self.check('offer_statuses', offer, "SELECT status,count(*) AS count FROM public.marketplace_offer GROUP BY status ORDER BY status")
        for kind, group, where in [('personal', 'listing_id,sender_id', 'organization_id IS NULL'), ('organization', 'listing_id,organization_id', 'organization_id IS NOT NULL')]:
            self.check(f'duplicate_{kind}_summary', offer, f"SELECT count(*) AS duplicate_groups, COALESCE(sum(n-1),0) AS excess_pending_offers FROM (SELECT count(*) AS n FROM public.marketplace_offer WHERE status='PENDING' AND {where} GROUP BY {group} HAVING count(*)>1) d")
            self.check(f'duplicate_{kind}_sample', offer, f"SELECT {group},count(*) AS pending_count,min(id) AS first_offer_id,max(id) AS last_offer_id FROM public.marketplace_offer WHERE status='PENDING' AND {where} GROUP BY {group} HAVING count(*)>1 ORDER BY min(id) LIMIT 20")
        valid_offer = "((status='PENDING' AND decided_at IS NULL AND talent_consented_at IS NULL) OR (status='ACCEPTED' AND decided_at IS NOT NULL AND talent_consented_at IS NOT NULL) OR (status IN ('DECLINED','WITHDRAWN') AND decided_at IS NOT NULL AND talent_consented_at IS NULL))"
        self.check('offer_decision_integrity', offer, f"SELECT count(*) FILTER (WHERE status NOT IN ('PENDING','ACCEPTED','DECLINED','WITHDRAWN')) AS invalid_status, count(*) FILTER (WHERE NOT {valid_offer}) AS inconsistent_decision_or_consent FROM public.marketplace_offer")
        self.check('offer_decision_sample', offer, f"SELECT id,status FROM public.marketplace_offer WHERE NOT {valid_offer} ORDER BY id LIMIT 20")
        membership = {'messaging_conversation': ['id'], 'messaging_conversationparticipant': ['conversation_id', 'user_id']}
        self.check('conversation_memberships', membership, "SELECT count(*) AS total_conversations,count(*) FILTER (WHERE members=0) AS zero_members,count(*) FILTER (WHERE members=1) AS one_member FROM (SELECT c.id,count(p.user_id) AS members FROM public.messaging_conversation c LEFT JOIN public.messaging_conversationparticipant p ON p.conversation_id=c.id GROUP BY c.id) counts")
        self.check('conversation_zero_member_sample', membership, "SELECT c.id FROM public.messaging_conversation c WHERE NOT EXISTS (SELECT 1 FROM public.messaging_conversationparticipant p WHERE p.conversation_id=c.id) ORDER BY c.id LIMIT 20")
        self.check('direct_room_membership_review', {**membership, 'messaging_conversation': ['id', 'is_group']}, "SELECT count(*) AS direct_rooms_with_fewer_than_two_members FROM public.messaging_conversation c WHERE NOT c.is_group AND (SELECT count(*) FROM public.messaging_conversationparticipant p WHERE p.conversation_id=c.id)<2")
        self.check('message_sender_membership_review', {**membership, 'messaging_message': ['conversation_id', 'sender_id']}, "SELECT count(*) AS historical_messages_from_current_nonmembers,count(DISTINCT m.conversation_id) AS rooms FROM public.messaging_message m WHERE NOT EXISTS (SELECT 1 FROM public.messaging_conversationparticipant p WHERE p.conversation_id=m.conversation_id AND p.user_id=m.sender_id)")
        self.check('creator_membership_review', {**membership, 'messaging_conversation': ['id', 'created_by_id']}, "SELECT count(*) AS creators_not_current_members FROM public.messaging_conversation c WHERE c.created_by_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM public.messaging_conversationparticipant p WHERE p.conversation_id=c.id AND p.user_id=c.created_by_id)")
        self.check('legacy_conversation_links', {'messaging_conversation': ['id', 'talent_id', 'organization_id'], 'talents_talentprofile': ['id', 'user_id'], 'organizations_organization': ['id', 'user_id']}, "SELECT count(*) AS conversations_with_legacy_links,count(*) FILTER (WHERE t.user_id IS NULL OR o.user_id IS NULL) AS unresolved_links FROM public.messaging_conversation c LEFT JOIN public.talents_talentprofile t ON t.id=c.talent_id LEFT JOIN public.organizations_organization o ON o.id=c.organization_id")
        calls = {'messaging_call': ['id', 'status', 'ended_at', 'answered_at']}
        self.check('call_statuses', calls, "SELECT status,count(*) AS count FROM public.messaging_call GROUP BY status ORDER BY status")
        self.check('legacy_call_status_summary', calls, "SELECT count(*) FILTER (WHERE status='ACCEPTED') AS accepted_legacy,count(*) FILTER (WHERE status='REJECTED') AS rejected_legacy,count(*) FILTER (WHERE status NOT IN ('RINGING','ACTIVE','ENDED','MISSED')) AS outside_current_choices,count(*) FILTER (WHERE status='ACTIVE' AND ended_at IS NOT NULL) AS active_with_end_timestamp FROM public.messaging_call")
        self.check('legacy_call_sample', calls, "SELECT id,status,answered_at IS NOT NULL AS has_answer_time,ended_at IS NOT NULL AS has_end_time FROM public.messaging_call WHERE status NOT IN ('RINGING','ACTIVE','ENDED','MISSED') ORDER BY id LIMIT 20")
        self.check('call_initiators', {'messaging_call': ['id', 'initiated_by_id']}, "SELECT count(*) FILTER (WHERE initiated_by_id IS NULL) AS missing_initiator FROM public.messaging_call")
        self.check('call_participants', {'messaging_call': ['id'], 'messaging_callparticipant': ['call_id', 'user_id', 'status']}, "SELECT count(*) AS total_calls,count(*) FILTER (WHERE members=0) AS calls_without_participants FROM (SELECT c.id,count(p.user_id) AS members FROM public.messaging_call c LEFT JOIN public.messaging_callparticipant p ON p.call_id=c.id GROUP BY c.id) counts")
        self.check('call_participant_statuses', {'messaging_callparticipant': ['status']}, "SELECT status,count(*) AS count FROM public.messaging_callparticipant GROUP BY status ORDER BY status")
        self.query('backup_postgres_settings', "SELECT name,setting FROM pg_catalog.pg_settings WHERE name IN ('archive_mode','wal_level','archive_timeout') ORDER BY name")
        self.query('archive_health', "SELECT archived_count,last_archived_time,failed_count,last_failed_time FROM pg_catalog.pg_stat_archiver")
        return self.checks


def ssh_report(identity_file=None):
    """Run the same reads inside the existing app container, without file writes."""
    production_dsn(require_public=False)
    local = sorted((p.parent.parent.name, p.stem) for p in ROOT.glob('*/migrations/[0-9]*.py'))
    source = '''import os,json,time
from datetime import datetime,timezone
import psycopg2
from psycopg2.extras import RealDictCursor
'''
    source += inspect.getsource(Reader)
    source += f'\nlocal_migrations = {local!r}\n'
    source += '''
report = {'captured_at_utc': datetime.now(timezone.utc).isoformat(),
          'scope': {'project': 'awinlink', 'environment': 'production', 'service': 'Postgres',
                    'route': 'existing_app_container', 'application_database_reference_verified': True},
          'read_only': True, 'checks': {}}
try:
    connection = psycopg2.connect(os.environ['DATABASE_URL'], connect_timeout=8, sslmode='require',
        application_name='awinlink_migration_audit_readonly',
        options='-c default_transaction_read_only=on -c statement_timeout=15000 -c lock_timeout=1000 -c idle_in_transaction_session_timeout=30000')
    try:
        connection.set_session(readonly=True, isolation_level='REPEATABLE READ')
        reader = Reader(connection, local_migrations)
        report['checks'] = reader.checks
        reader.run()
        report['result'] = 'queries_completed_review_findings'
    finally:
        connection.rollback()
        connection.close()
except Exception as error:
    report.update(result='incomplete', error_type=type(error).__name__)
print('AWINLINK_READONLY_RESULT=' + json.dumps(report,default=str))
'''
    compile(source, '<read-only-audit>', 'exec')
    payload = base64.b64encode(zlib.compress(source.encode())).decode('ascii')
    # The remote shell receives one quoted Python program; payload is base64,
    # never shell-interpolated credentials. -B disables bytecode file writes.
    remote = f"python -B -c 'import base64,zlib;exec(zlib.decompress(base64.b64decode(\"{payload}\")))'"
    args = ['railway.cmd', 'ssh', '--project', PROJECT,
            '--environment', ENVIRONMENT, '--service', APP_SERVICE]
    if identity_file:
        args.extend(['--identity-file', str(identity_file)])
    result = subprocess.run([*args, '--', remote],
        capture_output=True, text=True, timeout=125)
    for line in result.stdout.splitlines():
        if line.startswith('AWINLINK_READONLY_RESULT='):
            return json.loads(line.split('=', 1)[1])
    # Never relay arbitrary remote environment/CLI output.
    raise RuntimeError('Remote audit did not return its JSON marker; output withheld')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--railway-production', action='store_true')
    source.add_argument('--railway-production-ssh', action='store_true', help='Use the existing application container; writes no remote files')
    source.add_argument('--local-test-env', metavar='VARIABLE', help='Loopback-only test DSN from an environment variable')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--identity-file', type=Path, help='Existing authorized SSH identity; does not generate or register keys')
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT):
        parser.error('Audit output must remain in the workspace')
    if args.identity_file and (not args.railway_production_ssh or not args.identity_file.is_file()):
        parser.error('An existing identity file is supported only with --railway-production-ssh')
    if args.railway_production_ssh:
        try:
            report = ssh_report(args.identity_file)
        except Exception as error:
            report = {'captured_at_utc': datetime.now(timezone.utc).isoformat(),
                      'scope': {'project': 'awinlink', 'environment': 'production', 'route': 'existing_app_container'},
                      'result': 'incomplete', 'read_only': True, 'checks': {},
                      'error_type': type(error).__name__,
                      'note': 'Access or remote execution failed; no database checks can be claimed.'}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, default=str) + '\n', encoding='utf-8')
        print(json.dumps({'result': report['result'], 'checks': len(report['checks']), 'report': str(output)}))
        return 0 if report['result'] != 'incomplete' else 1
    if args.railway_production:
        dsn = production_dsn()
        scope = {'project': 'awinlink', 'environment': 'production', 'service': 'Postgres', 'application_database_reference_verified': True}
        sslmode = 'require'
    else:
        dsn = os.environ.get(args.local_test_env, '')
        if urlparse(dsn).hostname not in ('localhost', '127.0.0.1', '::1'):
            parser.error('Local tests require an explicit loopback DSN')
        scope = {'environment': 'local_test'}
        sslmode = 'prefer'
    report = {'captured_at_utc': datetime.now(timezone.utc).isoformat(), 'scope': scope,
              'read_only': True, 'checks': {}}
    try:
        connection = psycopg2.connect(dsn, connect_timeout=8, sslmode=sslmode,
            application_name='awinlink_migration_audit_readonly',
            options='-c default_transaction_read_only=on -c statement_timeout=15000 -c lock_timeout=1000 -c idle_in_transaction_session_timeout=30000')
        try:
            connection.set_session(readonly=True, isolation_level='REPEATABLE READ')
            reader = Reader(connection)
            report['checks'] = reader.checks
            reader.run()
            report['result'] = 'queries_completed_review_findings'
        finally:
            connection.rollback()
            connection.close()
    except Exception as error:
        report.update(result='incomplete', error_type=type(error).__name__)
        # Connection exceptions can contain credentials/host details: never serialize them.
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, default=str) + '\n', encoding='utf-8')
    print(json.dumps({'result': report['result'], 'checks': len(report['checks']), 'report': str(output)}))
    return 0 if report['result'] != 'incomplete' else 1


if __name__ == '__main__':
    raise SystemExit(main())

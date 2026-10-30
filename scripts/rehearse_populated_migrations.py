"""Rehearse synthetic populated upgrades on the verified workspace Postgres only.

Creates/drops only UUID-named databases owned by this invocation. Never reads
DATABASE_URL or dotenv. Dumps contain synthetic fixtures, never production data.
"""
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone as dt_timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

import psycopg2
from psycopg2 import sql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BIN = ROOT / '.audit-vc-tools/postgres/pgsql/bin'
DATA = ROOT / '.audit-vc-tools/postgres-data'
CONNECTION = dict(host='127.0.0.1', port=55432, user='vc_audit', connect_timeout=5,
                  options='-c statement_timeout=30000 -c lock_timeout=2000')


def canonical(value):
    return json.dumps(value, sort_keys=True, default=str, separators=(',', ':'))


def error_metadata(error):
    cause = getattr(error, '__cause__', None) or error
    return dict(error_type=type(error).__name__, sqlstate=getattr(cause, 'pgcode', None),
                constraint=getattr(getattr(cause, 'diag', None), 'constraint_name', None))


def main():
    runtime = {key: os.environ[key] for key in ('SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATH', 'TEMP', 'TMP') if key in os.environ}
    with patch.dict(os.environ, {**runtime, 'PYTHON_DOTENV_DISABLED': '1',
            'DJANGO_SETTINGS_MODULE': 'config.settings', 'AWINLINK_ENV': 'development', 'DEBUG': 'true',
            'SECRET_KEY': 'synthetic-migration-rehearsal-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ'}, clear=True), \
            patch('dotenv.load_dotenv', return_value=False):
        # Reuse historical fixture generators, not their main/database lifecycle.
        from scripts import talent_market_postgres_audit as legacy
        from django.conf import settings
        from django.core.cache import cache
        from django.db import connection, connections
        from config.migration_safety import SafeMigrationExecutor as MigrationExecutor
        from django.db.migrations.recorder import MigrationRecorder
        from django.test.runner import DiscoverRunner
        from django.utils import timezone

        settings.CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
        settings.AUTH_RATE_LIMIT_CACHE_ALIAS = settings.PASSWORD_RESET_CACHE_ALIAS = 'default'
        settings.AUTH_RATE_LIMIT_REQUIRE_SHARED_CACHE = False
        settings.AWINLINK_RESOURCE_CACHE_ALIAS = 'default'
        settings.CHANNEL_LAYERS = {'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}
        settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
        settings.WEB_PUSH_PUBLIC_KEY = settings.WEB_PUSH_PRIVATE_KEY = settings.MOBILE_APNS_PRIVATE_KEY = ''
        settings.PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
        settings.STORAGES = {'default': {'BACKEND': 'django.core.files.storage.InMemoryStorage'},
                            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}
        settings.MIDDLEWARE = [item for item in settings.MIDDLEWARE if not item.startswith('whitenoise.')]
        settings.DATABASES['default']['OPTIONS'] = {'options': '-c statement_timeout=30000 -c lock_timeout=2000'}

        admin = psycopg2.connect(dbname='postgres', **CONNECTION)
        admin.autocommit = True
        with admin.cursor() as cursor:
            cursor.execute('SHOW data_directory')
            if Path(cursor.fetchone()[0]).resolve() != DATA.resolve():
                raise RuntimeError('Refusing a PostgreSQL cluster outside the workspace audit directory')
            cursor.execute('SHOW server_version')
            version = cursor.fetchone()[0]
            # CREATE/DROP DATABASE may wait for a checkpoint on this Windows
            # fixture. Keep migration SQL budgets separate from fixture cleanup.
            cursor.execute('SET statement_timeout=900000')
        output = ROOT / '.audit-migration-rehearsal' / uuid4().hex
        output.mkdir(parents=True)
        report = dict(started_at_utc=datetime.now(dt_timezone.utc).isoformat(), postgres_version=version,
                      scope='Synthetic fixtures in UUID-named databases on verified loopback workspace cluster only',
                      cases=[], cleanup=[], artifact_directory=str(output.relative_to(ROOT)))
        owned = set()

        def emit(result):
            report['cases'].append(result)
            (output / 'report.json').write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
            print(canonical(result), flush=True)

        @contextmanager
        def database(label):
            name = 'awinlink_rehearsal_' + uuid4().hex
            with admin.cursor() as cursor:
                cursor.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
            owned.add(name)
            report.setdefault('created_databases', []).append(dict(case=label, name=name))
            connection.close()
            connection.settings_dict['NAME'] = settings.DATABASES['default']['NAME'] = name
            try:
                yield name
            finally:
                connections.close_all()
                if name not in owned or not name.startswith('awinlink_rehearsal_'):
                    raise RuntimeError('Refusing database cleanup outside this invocation')
                try:
                    with admin.cursor() as cursor:
                        cursor.execute(sql.SQL('DROP DATABASE IF EXISTS {}').format(sql.Identifier(name)))
                    owned.remove(name)
                    report['cleanup'].append(dict(case=label, dropped=True))
                except Exception as error:
                    report['cleanup'].append(dict(case=label, dropped=False, **error_metadata(error)))

        def select_database(name):
            if name not in owned:
                raise RuntimeError('Database was not created by this invocation')
            connection.close()
            connection.settings_dict['NAME'] = settings.DATABASES['default']['NAME'] = name

        def migrate(targets):
            executor = MigrationExecutor(connection)
            plan = executor.migration_plan(targets)
            started = time.monotonic()
            executor.migrate(targets)
            return dict(steps=len(plan), seconds=round(time.monotonic() - started, 3),
                        migrations=[f'{m.app_label}.{m.name}' for m, _ in plan])

        def apps():
            executor = MigrationExecutor(connection)
            applied = list(MigrationRecorder(connection).applied_migrations())
            return executor.loader.project_state(applied).apps

        def snapshot(include_recorder=False):
            result = {}
            with connection.cursor() as cursor:
                for table in sorted(connection.introspection.table_names()):
                    if table == 'django_migrations' and not include_recorder:
                        continue
                    cursor.execute(sql.SQL('SELECT * FROM {}').format(sql.Identifier(table)))
                    columns = [field[0] for field in cursor.description]
                    result[table] = {'columns': columns, 'rows': [dict(zip(columns, row)) for row in cursor.fetchall()]}
            return result

        def preservation(before):
            after = snapshot(include_recorder='django_migrations' in before)
            losses = []
            for table, original in before.items():
                if table not in after or not set(original['columns']) <= set(after[table]['columns']):
                    losses.append(dict(table=table, reason='table_or_columns_removed'))
                    continue
                old = Counter(canonical(row) for row in original['rows'])
                new = Counter(canonical({k: row[k] for k in original['columns']}) for row in after[table]['rows'])
                if old - new:
                    losses.append(dict(table=table, missing_or_changed_rows=sum((old - new).values())))
            return dict(preserved=not losses, original_rows=sum(len(t['rows']) for t in before.values()),
                        original_tables=len(before), losses=losses)

        def digest(rows):
            return hashlib.sha256(canonical({table: sorted(canonical(row) for row in data['rows'])
                                             for table, data in rows.items()}).encode()).hexdigest()

        def catalog():
            with connection.cursor() as cursor:
                cursor.execute("SELECT c.relname FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND (NOT i.indisvalid OR NOT i.indisready)")
                invalid = [row[0] for row in cursor.fetchall()]
                cursor.execute("SELECT conname FROM pg_constraint WHERE connamespace='public'::regnamespace AND NOT convalidated")
                unvalidated = [row[0] for row in cursor.fetchall()]
                cursor.execute("SELECT count(*) FROM pg_constraint WHERE connamespace='public'::regnamespace AND contype='f'")
                foreign_keys = cursor.fetchone()[0]
            return dict(invalid_indexes=invalid, unvalidated_constraints=unvalidated, foreign_keys=foreign_keys)

        def dump(name, filename):
            if name not in owned:
                raise RuntimeError('Refusing to dump a non-fixture database')
            path = output / filename
            command = [str(BIN / 'pg_dump.exe'), '-h', '127.0.0.1', '-p', '55432', '-U', 'vc_audit',
                       '-d', name, '--format=custom', '--no-owner', '--no-acl', '--lock-wait-timeout=2000', '-f', str(path)]
            completed = subprocess.run(command, capture_output=True, timeout=120, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            if completed.returncode:
                raise RuntimeError('Synthetic pg_dump failed; command output withheld')
            return path, dict(bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())

        def restore(name, path):
            if name not in owned or path.parent != output:
                raise RuntimeError('Restore source/target is outside this invocation')
            completed = subprocess.run([str(BIN / 'pg_restore.exe'), '-h', '127.0.0.1', '-p', '55432', '-U', 'vc_audit',
                '-d', name, '--no-owner', '--no-acl', '--exit-on-error', str(path)], capture_output=True, timeout=120,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            if completed.returncode:
                raise RuntimeError('Synthetic pg_restore failed; command output withheld')

        def seed_current(state):
            model = state.get_model
            owner, talent, learner, coach = [model('accounts', 'User').objects.create(username=f'rehearsal-{x}')
                                             for x in ['owner', 'talent', 'learner', 'coach']]
            org = model('organizations', 'Organization').objects.create(user_id=owner.pk, name='Synthetic academy', country='GH')
            model('organizations', 'OrganizationMembership').objects.create(organization_id=org.pk, user_id=owner.pk, role='OWNER')
            profile = model('talents', 'TalentProfile').objects.create(user_id=talent.pk, profile_visibility='PRIVATE')
            model('talents', 'VerificationRequest').objects.create(talent_id=profile.pk, document='verification_documents/synthetic.pdf')
            entry = model('organizations', 'OrganizationTalent').objects.create(organization_id=org.pk, talent_id=profile.pk,
                name='Synthetic affiliation', tag='Player', roster='2026', status='CONFIRMED')
            model('organizations', 'OrganizationTalentEvent').objects.create(affiliation_id=entry.pk, actor_id=talent.pk, action='CONFIRM', reason='Synthetic consent')
            agreement = model('organizations', 'TalentAgreement').objects.create(roster_entry_id=entry.pk, organization_id=org.pk,
                talent_id=profile.pk, kind='CONTRACT', status='ACTIVE', title='Synthetic agreement', terms='Synthetic terms',
                amount='120.00', currency='GHS', terms_hash='', activated_at=timezone.now(), created_by_id=owner.pk,
                roster_snapshot={'tag': 'Player', 'roster': '2026'})
            from organizations.agreement_services import hash_terms
            agreement.refresh_from_db()  # Canonical Decimal/date values for the consent digest.
            agreement.terms_hash = hash_terms(agreement)
            agreement.save(update_fields=['terms_hash'])
            for party, actor in [('ORIGIN', owner), ('TALENT', talent)]:
                model('organizations', 'TalentAgreementConsent').objects.create(agreement_id=agreement.pk, actor_id=actor.pk,
                    actor_name=actor.username, party=party, purpose='ACTIVATE', revision=1, terms_hash=agreement.terms_hash)
            category = model('learning', 'LearningCategory').objects.create(name='Sports', description='Preserve this custom description')
            course = model('learning', 'Course').objects.create(creator_id=owner.pk, category_id=category.pk,
                title='Synthetic course', slug='synthetic-course', description='Synthetic curriculum', status='APPROVED')
            lesson = model('learning', 'Lesson').objects.create(course_id=course.pk, title='Lesson', order=1, notes='learning/notes/synthetic.pdf')
            enrollment = model('learning', 'Enrollment').objects.create(user_id=learner.pk, course_id=course.pk)
            model('learning', 'LessonProgress').objects.create(enrollment_id=enrollment.pk, lesson_id=lesson.pk, completed=True)
            room = model('messaging', 'Conversation').objects.create(created_by_id=owner.pk)
            for user in [owner, talent]:
                model('messaging', 'ConversationParticipant').objects.create(conversation_id=room.pk, user_id=user.pk)
            for number in range(100):
                model('messaging', 'Message').objects.create(conversation_id=room.pk, sender_id=owner.pk, content=f'Synthetic message {number}')
            call = model('messaging', 'Call').objects.create(conversation_id=room.pk, initiated_by_id=owner.pk,
                status='ENDED', call_type='VOICE', ended_at=timezone.now())
            for user in [owner, talent]:
                model('messaging', 'CallParticipant').objects.create(call_id=call.pk, user_id=user.pk, status='LEFT')
            domain = model('domains', 'TalentDomain').objects.create(name='Synthetic domain')
            listing = model('marketplace', 'Listing').objects.create(talent_id=profile.pk, subecosystem_id=domain.pk,
                ecosystem='SPORTS', title='Synthetic listing', status='PUBLISHED', publication_consented_at=timezone.now())
            now = timezone.now()
            offer = model('marketplace', 'Offer').objects.create(listing_id=listing.pk, sender_id=owner.pk,
                terms='Synthetic agreed terms', status='ACCEPTED', decided_at=now, talent_consented_at=now)
            booking = model('marketplace', 'Booking').objects.create(offer_id=offer.pk, talent_id=profile.pk,
                starts_at=now+timedelta(days=1), ends_at=now+timedelta(days=1, hours=1),
                busy_start=now+timedelta(days=1), busy_end=now+timedelta(days=1, hours=1),
                amount='120.00', currency='GHS', snapshot={'terms': 'Synthetic agreed terms'})
            model('marketplace', 'BookingEvent').objects.create(booking_id=booking.pk, actor_id=talent.pk, action='CONFIRMED', reason='Synthetic history')
            return dict(org=org.pk, coach_user=coach.pk)

        def legacy_cases():
            probes = [('market_clean', ('marketplace', '0001_initial'), ('marketplace', '0002_workflow_guards'), lambda state: legacy.market(state, 'clean')),
                *[(f'market_{v}', ('marketplace', '0001_initial'), ('marketplace', '0002_workflow_guards'), lambda state, v=v: legacy.market(state, v))
                  for v in ['duplicate_personal', 'duplicate_organization', 'missing_consent']],
                ('messaging_participants', ('messaging', '0005_message_video'), ('messaging', '0006_alter_conversation_unique_together_and_more'), legacy.conversation),
                ('messaging_calls', ('messaging', '0009_conversation_created_by_conversation_image_and_more'), ('messaging', '0010_remove_call_caller_remove_call_receiver_and_more'), legacy.calls),
                ('messaging_read_history', ('messaging', '0011_message_reply_to'), ('messaging', '0012_conversationparticipant_last_read_at'), legacy.read_history)]
            for label, before, after, seed in probes:
                result = dict(case=label)
                with database(label):
                    try:
                        migrate([before])
                        verify = seed(apps())
                        original = snapshot()
                        try:
                            result['upgrade'] = migrate([after])
                            result['verification'] = verify(apps())
                            result['original_rows'] = preservation(original)
                        except Exception as error:
                            result['upgrade_error'] = error_metadata(error)
                            result['failure_preserved_original_rows'] = preservation(original)
                        if 'upgrade' in result and label in ('messaging_participants', 'messaging_calls'):
                            upgraded = snapshot(include_recorder=True)
                            try:
                                result['rollback'] = migrate([before])
                                result['rollback_preserved_original_rows'] = preservation(original)
                            except Exception as error:
                                result['rollback_error'] = error_metadata(error)
                                result['rollback_failure_preserved_upgraded_rows'] = preservation(upgraded)
                    except Exception as error:
                        result['fixture_error'] = error_metadata(error)
                emit(result)

        def populated_case():
            with database('current_populated_upgrade') as name:
                executor = MigrationExecutor(connection)
                latest = executor.loader.graph.leaf_nodes()
                cuts = [('organizations', '0014_coach_scout_roster_badges'), ('learning', '0014_seed_course_categories'),
                        ('messaging', '0013_resource_pagination_indexes'), ('recommendations', '0003_rising_talent_intelligence'),
                        ('talents', '0016_rising_job_indexes'), ('media_erasure', '0001_initial')]
                excluded = set().union(*(set(executor.loader.graph.backwards_plan(cut)) for cut in cuts))
                included = set(executor.loader.graph.nodes) - excluded
                before = [key for key in included if not any(child.key in included for child in executor.loader.graph.node_map[key].children)]
                migrate(before)
                ids = seed_current(apps())
                original = snapshot()
                full_before = snapshot(include_recorder=True)
                archive, archive_info = dump(name, 'synthetic-before-upgrade.dump')
                upgrade = migrate(latest)
                integrity = preservation(original)
                emit(dict(case='current_populated_upgrade', upgrade=upgrade, integrity=integrity, catalog=catalog(), backup=archive_info))

                with database('restore_preupgrade_backup') as restored:
                    restore(restored, archive)
                    select_database(restored)
                    restored_before = snapshot(include_recorder=True)
                    exact = digest(restored_before) == digest(full_before)
                    restored_upgrade = migrate(latest)
                    emit(dict(case='preupgrade_backup_restore_and_upgrade', exact_rows_and_migration_history=exact,
                              upgrade=restored_upgrade, integrity=preservation(original), catalog=catalog()))
                    # A retained coach link makes organization rollback intentionally unsafe.
                    current = apps()
                    coach = current.get_model('coaches', 'CoachProfile').objects.create(user_id=ids['coach_user'])
                    current.get_model('organizations', 'OrganizationTalent').objects.create(organization_id=ids['org'], coach_id=coach.pk,
                        name='Synthetic coach', tag='Coach', status='REMOVED')
                    before_guard = snapshot()
                    applied_before = set(MigrationRecorder(connection).applied_migrations())
                    try:
                        rollback = dict(succeeded=True, details=migrate([('organizations', '0013_roster_agreements')]))
                    except Exception as error:
                        rollback = dict(succeeded=False, **error_metadata(error))
                    applied_after = set(MigrationRecorder(connection).applied_migrations())
                    emit(dict(case='coach_consent_rollback_guard', rollback=rollback, integrity=preservation(before_guard),
                              already_unapplied_before_guard=[f'{a}.{n}' for a, n in sorted(applied_before-applied_after)]))
                select_database(name)

        def regression_tests():
            with database('postgres_migration_regressions') as name:
                connection.settings_dict['TEST']['NAME'] = name
                labels = ['marketplace.test_migrations', 'marketplace.test_phase_two_migrations',
                    'marketplace.test_booking_overlap_migration', 'marketplace.test_postgresql',
                    'marketplace.test_phase_two_postgresql', 'marketplace.test_payments_postgresql',
                    'organizations.test_membership_migrations', 'organizations.test_profile_badges.ProfileBadgeMigrationTests',
                    'organizations.test_roster_postgresql', 'organizations.test_agreement_postgresql',
                    'learning.test_vc_migrations', 'learning.test_classroom_service_migrations']
                if '--agreement-tests-only' in sys.argv:
                    labels = ['organizations.test_agreement_postgresql']
                if '--safety-tests-only' in sys.argv:
                    labels = ['messaging.test_migration_safety']
                if '--index-tests-only' in sys.argv:
                    labels = ['messaging.test_migration_safety.MigrationSafetyTests.test_concurrent_index_forward_reverse_retries_and_collision']
                if '--learning-workflow-tests-only' in sys.argv:
                    labels = ['learning.test_workflow_rules']

                class Result(unittest.TextTestResult):
                    def startTest(self, test):
                        cache.clear()
                        super().startTest(test)

                class Runner(DiscoverRunner):
                    def get_resultclass(self):
                        return Result

                    def run_suite(self, suite, **kwargs):
                        result = super().run_suite(suite, **kwargs)
                        self.summary = dict(run=result.testsRun, failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped))
                        return result

                # The outer context owns this freshly-created UUID database.
                # Avoid Django's separate DROP with the migration SQL timeout;
                # the verified lifecycle connection handles cleanup instead.
                runner = Runner(verbosity=1, interactive=False, keepdb=True)
                failures = runner.run_tests(labels)
                emit(dict(case='postgres_migration_regressions', successful=not failures, **runner.summary))
                return failures

        def index_recovery():
            with database('concurrent_index_interruption'):
                prior = [('learning', '0013_classroom_chat')]
                category_target = [('learning', '0014_seed_course_categories')]
                target = [('learning', '0015_resource_pagination_indexes')]
                migrate(prior)
                state = apps()
                user = state.get_model('accounts', 'User').objects.create(username='index-rehearsal-owner')
                category = state.get_model('learning', 'LearningCategory').objects.create(name='Sports', description='Custom description')
                course = state.get_model('learning', 'Course').objects.create(creator_id=user.pk, category_id=category.pk,
                    title='Index fixture', slug='index-fixture', description='Synthetic course')
                lesson = state.get_model('learning', 'Lesson')
                lesson.objects.bulk_create([lesson(course_id=course.pk, title=f'Lesson {i}', order=i) for i in range(1, 51)])
                original = snapshot()
                migrate(category_target)
                migrate(prior)
                emit(dict(case='course_category_rollback', integrity=preservation(original),
                    categories_retained=apps().get_model('learning', 'LearningCategory').objects.count()))
                migrate(category_target)
                calls = 0

                def interrupt(execute, statement, params, many, context):
                    nonlocal calls
                    if str(statement).upper().startswith('CREATE INDEX CONCURRENTLY'):
                        calls += 1
                        if calls == 2:
                            raise RuntimeError('Synthetic interruption after one committed concurrent index')
                    return execute(statement, params, many, context)

                with connection.cursor() as cursor:
                    cursor.execute("SELECT indexname FROM pg_indexes WHERE schemaname='public'")
                    existing = {row[0] for row in cursor.fetchall()}
                try:
                    with connection.execute_wrapper(interrupt):
                        migrate(target)
                except Exception as error:
                    interruption = error_metadata(error)
                else:
                    raise RuntimeError('Index interruption fixture did not exercise both index operations')
                with connection.cursor() as cursor:
                    cursor.execute("SELECT indexname FROM pg_indexes WHERE schemaname='public'")
                    remaining = {row[0] for row in cursor.fetchall()} - existing
                recorded = ('learning', '0015_resource_pagination_indexes') in MigrationRecorder(connection).applied_migrations()
                try:
                    migrate(target)
                except Exception as error:
                    retry = dict(succeeded=False, **error_metadata(error))
                else:
                    retry = dict(succeeded=True)
                if remaining != {'learning_lesson_page_idx'}:
                    raise RuntimeError('Unexpected fixture index set; refusing index cleanup')
                if not retry['succeeded']:
                    raise RuntimeError('Catalog-verified index retry did not recover')
                recovered = migrate(target)
                emit(dict(case='concurrent_index_interruption_and_recovery', interruption=interruption,
                    index_left_committed=sorted(remaining), migration_recorded_after_interruption=recorded,
                    unassisted_retry=retry, repaired_fixture_upgrade=recovered,
                    integrity=preservation(original), catalog=catalog()))

        failures = 0
        try:
            if any(flag in sys.argv for flag in ['--agreement-tests-only', '--safety-tests-only', '--index-tests-only', '--learning-workflow-tests-only']):
                failures += regression_tests()
            elif '--index-recovery-only' in sys.argv:
                index_recovery()
            elif '--populated-only' in sys.argv:
                try:
                    populated_case()
                except Exception as error:
                    if '--trace-errors' in sys.argv:
                        import traceback
                        traceback.print_exc()
                    emit(dict(case='current_populated_rehearsal', fixture_error=error_metadata(error)))
                    failures += 1
            else:
                legacy_cases()
                try:
                    populated_case()
                except Exception as error:
                    if '--trace-errors' in sys.argv:
                        import traceback
                        traceback.print_exc()
                    emit(dict(case='current_populated_rehearsal', fixture_error=error_metadata(error)))
                    failures += 1
                failures += regression_tests()
        finally:
            admin.close()
            report['completed_at_utc'] = datetime.now(dt_timezone.utc).isoformat()
            report['databases_left_owned'] = len(owned)
            (output / 'report.json').write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
            print(canonical(dict(report=str((output / 'report.json').relative_to(ROOT)), databases_left_owned=len(owned))), flush=True)
        return bool(failures or owned or any('fixture_error' in case for case in report['cases']))


if __name__ == '__main__':
    raise SystemExit(main())

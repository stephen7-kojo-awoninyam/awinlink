"""Read-only Railway backup metadata. Never creates/restores backups or runs SQL."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.railway_migration_audit import railway_json, PROJECT, ENVIRONMENT, SERVICE, production_dsn

BACKUP_QUERY = '''query SecurityBackupReadiness($volume: String!) {
  backups: volumeInstanceBackupList(volumeInstanceId: $volume) { id createdAt expiresAt }
  schedules: volumeInstanceBackupScheduleList(volumeInstanceId: $volume) { kind retentionSeconds }
}'''


class BackupCheckUnavailable(Exception):
    pass


def backup_metadata(volume_id):
    # The document is fixed: no arbitrary GraphQL, mutations, variables, or keys.
    result = subprocess.run(['railway.cmd', 'api', '--file', '-', '--variables',
        json.dumps({'volume': volume_id}), '--compact'], input=BACKUP_QUERY,
        capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise BackupCheckUnavailable('Backup metadata could not be read; CLI output withheld.')
    try:
        result = json.loads(result.stdout)
        if result.get('errors'):
            raise ValueError()
        data = result.get('data', result)
        if not isinstance(data['backups'], list) or not isinstance(data['schedules'], list):
            raise ValueError()
        return data
    except (ValueError, KeyError, TypeError):
        raise BackupCheckUnavailable('Incomplete backup metadata; no clean result assumed.') from None


def summarize(data, now):
    valid = []
    for backup in data['backups']:
        try:
            created = datetime.fromisoformat(backup['createdAt'].replace('Z', '+00:00'))
            expires = datetime.fromisoformat(backup['expiresAt'].replace('Z', '+00:00')) if backup.get('expiresAt') else None
            if created.tzinfo is None or (expires is not None and expires.tzinfo is None):
                raise ValueError()
            if expires is None or expires > now:
                valid.append(created)
        except (ValueError, KeyError, TypeError):
            raise BackupCheckUnavailable('Backup timestamps could not be verified.') from None
    fresh = any(0 <= (now - created).total_seconds() <= 86400 for created in valid)
    return {'backup_count': len(data['backups']), 'unexpired_backup_count': len(valid),
        'fresh_backup_within_24_hours': fresh, 'schedule_count': len(data['schedules']),
        'pitr_status': 'not_verified_by_this_metadata_query', 'restore_verified': False,
        'status': 'BLOCKED',
        'blockers': ([] if fresh else ['No verified unexpired backup from the last 24 hours.'])
                    + ([] if data['schedules'] else ['No Railway backup schedule configured.'])
                    + ['A restore rehearsal and recovery objectives still require operator verification.']}


def pitr_metadata():
    try:
        result = subprocess.run(['railway.cmd', 'postgres', '--project', PROJECT,
            '--environment', ENVIRONMENT, '--service', SERVICE, '--json', 'pitr', 'status'],
            capture_output=True, text=True, timeout=45)
        if result.returncode:
            return {'pitr_status': 'inconclusive'}
        data = json.loads(result.stdout)
        enabled = data.get('enabled')
        return {'pitr_status': 'enabled' if enabled is True else 'disabled' if enabled is False else 'inconclusive',
                'pitr_archive_wired': data.get('bucketWired') is True}
    except (ValueError, OSError, subprocess.TimeoutExpired):
        return {'pitr_status': 'inconclusive'}


def check():
    # Reuse the existing strict production identity and DB-reference checks.
    # DSNs stay in memory and are never printed; no database connection is made.
    production_dsn(require_public=False)
    status = railway_json('status')
    if status.get('id') != PROJECT:
        raise BackupCheckUnavailable('Project identity mismatch.')
    environment = next((e['node'] for e in status['environments']['edges'] if e['node']['id'] == ENVIRONMENT), None)
    if environment is None or environment['name'] != 'production':
        raise BackupCheckUnavailable('Production environment could not be verified.')
    volumes = [e['node'] for e in environment.get('volumeInstances', {}).get('edges', []) if e['node'].get('serviceId') == SERVICE]
    if len(volumes) != 1:
        raise BackupCheckUnavailable('Expected exactly one audited Postgres volume.')
    now = datetime.now(timezone.utc)
    return {'checked_at_utc': now.isoformat(), 'environment': 'production', 'service': 'Postgres',
            'read_only': True, **summarize(backup_metadata(volumes[0]['id']), now), **pitr_metadata()}


if __name__ == '__main__':
    try:
        report = check()
    except Exception:
        report = {'status': 'INCONCLUSIVE', 'read_only': True, 'detail': 'Backup readiness could not be verified; no changes made and sensitive errors withheld.'}
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['status'] == 'READY' else 1)

"""Read-only configuration, Git, migration and secret-hygiene inventory."""
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
django.setup()
from django.conf import settings
from django.db.migrations.loader import MigrationLoader

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).splitlines()

loader = MigrationLoader(None)
loader.graph.validate_consistency()
tracked = git('ls-files')
untracked = git('ls-files', '--others', '--exclude-standard')
secret_findings = []
for name in tracked + untracked:
    path = ROOT / name
    if path.suffix in {'.pem', '.key'} or path.name == '.env':
        secret_findings.append({'file': name, 'issue': 'tracked secret container'})
    if path.suffix not in {'.py', '.js', '.ts', '.tsx', '.json', '.html', '.md', '.txt'}:
        continue
    try:
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if re.search(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|AKIA[0-9A-Z]{16}|sk_live_[A-Za-z0-9]{15,}', line):
                secret_findings.append({'file': name, 'line': number, 'issue': 'potential credential; value redacted'})
    except (UnicodeError, OSError):
        pass

env_names = []
if (ROOT / '.env').exists():
    env_names = [match.group(1) for line in (ROOT / '.env').read_text().splitlines()
                 if (match := re.match(r'\s*([A-Za-z_][A-Za-z0-9_]*)\s*=', line))]

report = {
    'git_status': git('status', '--short'),
    'staged': git('diff', '--cached', '--name-only'),
    'tracked_deployment_files': [name for name in tracked if re.search(r'railway|Procfile|Dockerfile|nixpacks|render\.ya', name, re.I)],
    'secret_findings_redacted': secret_findings,
    'source_files_scanned': len(tracked + untracked),
    'local_env_variable_names_only': env_names,
    'migration_count': len(loader.disk_migrations),
    'migration_conflicts': loader.detect_conflicts(),
    'migration_leaves': loader.graph.leaf_nodes(),
    'runtime': {
        'django': django.get_version(), 'debug': settings.DEBUG,
        'database_engine': settings.DATABASES['default']['ENGINE'],
        'channel_backend': settings.CHANNEL_LAYERS['default']['BACKEND'],
        'email_backend': settings.EMAIL_BACKEND,
        'secret_is_development_fallback': settings.SECRET_KEY == 'local-development-secret-change-this',
        'secure_ssl_redirect': settings.SECURE_SSL_REDIRECT,
        'session_cookie_secure': settings.SESSION_COOKIE_SECURE,
        'csrf_cookie_secure': settings.CSRF_COOKIE_SECURE,
    },
}
(ROOT / 'audit-inventory.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps({key: report[key] for key in ('staged', 'tracked_deployment_files', 'secret_findings_redacted', 'migration_count', 'migration_conflicts', 'runtime')}, indent=2))

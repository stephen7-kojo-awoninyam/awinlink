"""Read Railway SMTP/Resend configuration without sending mail or printing values."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.email_settings import email_settings
from accounts.email_configuration import inspect_email_configuration


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--environment', required=True)
    parser.add_argument('--service', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT):
        parser.error('Output must remain inside the workspace')
    result = subprocess.run(['railway.cmd', 'variable', 'list', '--project', args.project,
        '--environment', args.environment, '--service', args.service, '--json'],
        capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise SystemExit('Railway configuration read failed; output withheld. No email sent.')
    values = json.loads(result.stdout)
    if (values.get('RAILWAY_PROJECT_ID') != args.project
            or values.get('RAILWAY_ENVIRONMENT_ID') != args.environment
            or values.get('RAILWAY_SERVICE_ID') != args.service
            or values.get('RAILWAY_ENVIRONMENT_NAME') != 'production'):
        raise SystemExit('Production service identity mismatch; no further checks performed.')
    report = {'captured_at_utc': datetime.now(timezone.utc).isoformat(),
              'environment': 'production', 'read_only_metadata': True,
              'smtp_connection_attempted': False, 'emails_sent': 0}
    report['api_request_attempted'] = False
    report['configured'] = {name: bool(values.get(name, '')) for name in (
        'EMAIL_HOST', 'EMAIL_HOST_USER', 'EMAIL_HOST_PASSWORD', 'DEFAULT_FROM_EMAIL',
        'EMAIL_SENDER_DOMAIN', 'PASSWORD_RESET_BASE_URL', 'REDIS_URL', 'EMAIL_PROVIDER', 'RESEND_API_KEY')}
    try:
        debug = values.get('DEBUG', 'false').lower() == 'true'
        config = email_settings(values, production=not debug)
        config['PASSWORD_RESET_BASE_URL'] = values.get('PASSWORD_RESET_BASE_URL',
            'http://localhost:8000' if debug else 'https://' + values.get('RAILWAY_PUBLIC_DOMAIN',
                'awinlink-production.up.railway.app')).rstrip('/')
        report['readiness'] = inspect_email_configuration(SimpleNamespace(**config))
    except Exception as error:
        report['readiness'] = {'configuration_valid': False,
            'error_type': type(error).__name__, 'details': 'Invalid settings; values withheld.'}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if report['readiness']['configuration_valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

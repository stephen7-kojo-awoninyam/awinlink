"""Compile PostgreSQL DDL offline. This does not connect or execute SQL."""
import json
import os
from pathlib import Path
from unittest.mock import patch

os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
django.setup()
from django.apps import apps
from django.db.backends.postgresql.base import DatabaseWrapper
from django.db.migrations.loader import MigrationLoader

ROOT = Path(__file__).resolve().parent
database = DatabaseWrapper({
    'ENGINE': 'django.db.backends.postgresql', 'NAME': 'awinlink_audit_offline',
    'USER': '', 'PASSWORD': '', 'HOST': '', 'PORT': '', 'OPTIONS': {},
    'AUTOCOMMIT': True, 'ATOMIC_REQUESTS': False, 'CONN_MAX_AGE': 0,
    'CONN_HEALTH_CHECKS': False, 'TIME_ZONE': None,
}, alias='audit_offline')
database.pg_version = 170000
compiled = []
with patch.object(database, 'ensure_connection', side_effect=AssertionError('Network access prohibited in offline audit')):
    for model in apps.get_models():
        if not model._meta.managed or model._meta.proxy:
            continue
        with database.schema_editor(collect_sql=True, atomic=False) as editor:
            editor.create_model(model)
        compiled.extend(editor.collected_sql)
loader = MigrationLoader(None)
new_models = [
    ('organizations', '0009_organization_membership', 'OrganizationMembership'),
    ('organizations', '0011_organization_team_invitation', 'OrganizationTeamInvitation'),
    ('notifications', '0009_mobile_push_tokens', 'MobilePushToken'),
]
historical = {}
for app_label, migration, model_name in new_models:
    model = loader.project_state([(app_label, migration)]).apps.get_model(app_label, model_name)
    with patch.object(database, 'ensure_connection', side_effect=AssertionError('Network access prohibited')):
        with database.schema_editor(collect_sql=True, atomic=False) as editor:
            editor.create_model(model)
    historical[f'{app_label}.{migration}'] = editor.collected_sql
report = {'mode': 'OFFLINE compilation only; no PostgreSQL server or migration execution',
          'assumed_postgresql_version': 17, 'models': len(list(apps.get_models())),
          'ddl_statements': len(compiled), 'new_migration_model_ddl': historical}
(ROOT / 'audit-postgresql.json').write_text(json.dumps(report, indent=2))
print(json.dumps({key: report[key] for key in ('mode', 'assumed_postgresql_version', 'models', 'ddl_statements')}, indent=2))

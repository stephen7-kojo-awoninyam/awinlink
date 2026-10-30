"""Read-only whole-plan rollback checks. No DDL or invented repair data."""
from django.db import migrations
from django.db.migrations.exceptions import IrreversibleError
from django.db.migrations.executor import MigrationExecutor


def check_reverse_plan(connection, plan):
    backwards = [migration for migration, reverse in plan if reverse]
    if not backwards:
        return
    tables = set(connection.introspection.table_names())
    for migration in backwards:
        for operation in migration.operations:
            if not operation.reversible:
                raise IrreversibleError(f'Reverse plan includes irreversible {migration}; no migrations were reversed.')
            # Reversing a CreateModel otherwise silently drops post-release
            # records, including retention jobs and legal holds.
            if isinstance(operation, migrations.CreateModel):
                table = operation.options.get('db_table', f'{migration.app_label}_{operation.name.lower()}')
                if table in tables:
                    with connection.cursor() as cursor:
                        cursor.execute(f'SELECT 1 FROM {connection.ops.quote_name(table)} LIMIT 1')
                        if cursor.fetchone():
                            raise IrreversibleError(f'Reverse plan would drop populated table {table}; no migrations were reversed.')
        if migration.app_label == 'organizations' and migration.name == '0014_coach_scout_roster_badges':
            table = 'organizations_organizationtalent'
            with connection.cursor() as cursor:
                cursor.execute(f'SELECT 1 FROM {connection.ops.quote_name(table)} WHERE coach_id IS NOT NULL OR scout_id IS NOT NULL LIMIT 1')
                if cursor.fetchone():
                    raise IrreversibleError('Coach/scout history prevents this entire reverse plan; no migrations were reversed.')


def preflight_reverse(sender, using, plan, **kwargs):
    from django.db import connections
    check_reverse_plan(connections[using], plan)


class SafeMigrationExecutor(MigrationExecutor):
    """Use for programmatic migration execution (commands also use the signal)."""
    def migrate(self, targets, plan=None, state=None, fake=False, fake_initial=False):
        if plan is None:
            plan = self.migration_plan(targets)
        check_reverse_plan(self.connection, plan)
        return super().migrate(targets, plan=plan, state=state, fake=fake, fake_initial=fake_initial)

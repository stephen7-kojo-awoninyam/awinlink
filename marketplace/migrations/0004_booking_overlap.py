"""Database overlap protection; SQLite retains service-level validation only."""
import django.contrib.postgres.constraints
import django.contrib.postgres.fields.ranges
from django.contrib.postgres.operations import BtreeGistExtension
from django.db import migrations, models


class PostgresBtreeGistExtension(BtreeGistExtension):
    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        # Django guards forwards by vendor, but its reverse operation queries
        # pg_extension even on SQLite. Keep both directions PostgreSQL-only.
        if schema_editor.connection.vendor == 'postgresql':
            super().database_backwards(app_label, schema_editor, from_state, to_state)


class PostgresConstraint(migrations.AddConstraint):
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor == 'postgresql':
            super().database_forwards(app_label, schema_editor, from_state, to_state)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor == 'postgresql':
            super().database_backwards(app_label, schema_editor, from_state, to_state)


class Migration(migrations.Migration):
    dependencies = [('marketplace', '0003_phase_two')]
    operations = [
        PostgresBtreeGistExtension(),
        PostgresConstraint(
            model_name='booking',
            constraint=django.contrib.postgres.constraints.ExclusionConstraint(condition=models.Q(('status', 'CANCELLED'), _negated=True), expressions=[('talent', '='), (models.Func('busy_start', 'busy_end', models.Value('[)'), function='TSTZRANGE', output_field=django.contrib.postgres.fields.ranges.DateTimeRangeField()), '&&')], name='market_booking_no_overlap'),
        ),
    ]

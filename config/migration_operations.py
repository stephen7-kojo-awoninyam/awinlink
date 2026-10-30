"""Concurrent indexes with catalog-verified interrupted-operation recovery."""
import re
from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, NotSupportedError


class OnlineIndex(migrations.AddIndex):
    atomic = False

    def _existing(self, schema_editor, model):
        """Return readiness only for an exact plain index; refuse name collisions."""
        connection = schema_editor.connection
        with connection.cursor() as cursor:
            cursor.execute('''
                SELECT i.indisvalid, i.indisready, i.indislive,
                       i.indrelid = to_regclass(%s), am.amname,
                       i.indisunique, i.indisexclusion, i.indpred IS NULL,
                       i.indexprs IS NULL, i.indnatts, i.indnkeyatts,
                       ARRAY(SELECT pg_get_indexdef(c.oid, n, true)
                             FROM generate_series(1, i.indnkeyatts) n),
                       EXISTS(SELECT 1 FROM pg_constraint WHERE conindid=c.oid),
                       c.reltablespace, i.indoption::text,
                       NOT EXISTS (
                           SELECT 1 FROM unnest(i.indkey) WITH ORDINALITY k(attnum, n)
                           JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=k.attnum
                           JOIN pg_opclass opc ON opc.oid=i.indclass[k.n::int-1]
                           WHERE NOT opc.opcdefault OR i.indcollation[k.n::int-1]<>a.attcollation
                       ), c.reloptions IS NULL, c.oid=to_regclass(%s),
                       EXISTS(SELECT 1 FROM pg_stat_progress_create_index WHERE index_relid=c.oid),
                       i.indisclustered
                FROM pg_class c JOIN pg_namespace ns ON ns.oid=c.relnamespace
                JOIN pg_index i ON i.indexrelid=c.oid
                JOIN pg_am am ON am.oid=c.relam
                WHERE ns.oid=(SELECT relnamespace FROM pg_class WHERE oid=to_regclass(%s))
                  AND c.relname=%s
            ''', [model._meta.db_table, self.index.name, model._meta.db_table, self.index.name])
            row = cursor.fetchone()
            if row is None:
                # A same-named non-index relation must not be mistaken for absence.
                cursor.execute('''SELECT 1 FROM pg_class WHERE relname=%s AND relnamespace=
                    (SELECT relnamespace FROM pg_class WHERE oid=to_regclass(%s))''',
                    [self.index.name, model._meta.db_table])
                if cursor.fetchone():
                    raise NotSupportedError('Online index name conflicts with a non-index relation.')
                return None
        index = self.index
        expected = []
        for field_name, order in index.fields_orders:
            column = model._meta.get_field(field_name).column
            # Restrict automatic recovery to the simple index form we can prove.
            if not re.fullmatch(r'[a-z_][a-z_0-9]*', column):
                raise NotSupportedError('Index recovery requires reviewed identifier quoting.')
            expected.append(column)
        ordering = ' '.join('3' if order else '0' for _, order in index.fields_orders)
        plain = (not index.expressions and not index.condition and not index.include
                 and not index.opclasses and not index.db_tablespace)
        matches = (plain and row[3] and row[4] == 'btree' and not row[5] and not row[6]
                   and row[7] and row[8] and row[9] == row[10] == len(expected)
                   and [value.replace('"', '') for value in row[11]] == expected
                   and not row[12] and row[13] == 0 and row[14] == ordering and row[15] and row[16]
                   and row[17] and not row[18] and not row[19])
        if not matches:
            raise NotSupportedError(f'Existing index {index.name} differs from the migration; refusing automatic recovery.')
        return all(row[:3])

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor == 'postgresql':
            operation = AddIndexConcurrently(self.model_name, self.index)
            operation._ensure_not_in_transaction(schema_editor)
            model = to_state.apps.get_model(app_label, self.model_name)
            if not self.allow_migrate_model(schema_editor.connection.alias, model):
                return
            existing = self._existing(schema_editor, model)
            if existing is True:
                return
            if existing is False:
                # Failed CREATE INDEX CONCURRENTLY can leave an invalid index.
                # Only the exact non-constraint definition above may be rebuilt.
                schema_editor.remove_index(model, self.index, concurrently=True)
            return AddIndexConcurrently(self.model_name, self.index).database_forwards(
                app_label, schema_editor, from_state, to_state)
        return super().database_forwards(app_label, schema_editor, from_state, to_state)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor == 'postgresql':
            operation = AddIndexConcurrently(self.model_name, self.index)
            operation._ensure_not_in_transaction(schema_editor)
            model = from_state.apps.get_model(app_label, self.model_name)
            if not self.allow_migrate_model(schema_editor.connection.alias, model):
                return
            if self._existing(schema_editor, model) is None:
                return
            return AddIndexConcurrently(self.model_name, self.index).database_backwards(
                app_label, schema_editor, from_state, to_state)
        return super().database_backwards(app_label, schema_editor, from_state, to_state)

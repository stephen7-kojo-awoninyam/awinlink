"""Offline safety tests; no Railway or database connections."""
import unittest
from unittest.mock import patch

import psycopg2
from scripts import railway_migration_audit as audit


class Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.statement = ''

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, statement, params=()):
        self.statement = statement
        self.connection.statements.append(statement)
        if statement == 'SELECT failure':
            raise psycopg2.ProgrammingError('sensitive-error-text')

    def fetchall(self):
        if 'transaction_read_only' in self.statement:
            return [{'read_only': self.connection.read_only, 'isolation': 'repeatable read'}]
        return []


class Connection:
    def __init__(self, read_only='on'):
        self.statements = []
        self.read_only = read_only

    def cursor(self, **kwargs):
        return Cursor(self)


class AuditSafetyTests(unittest.TestCase):
    def test_mutation_statements_are_refused_before_execution(self):
        connection = Connection()
        reader = audit.Reader(connection)
        for statement in ['UPDATE t SET x=1', 'DELETE FROM t', 'CREATE TABLE t(x int)', 'ALTER TABLE t ADD x int']:
            with self.assertRaises(ValueError):
                reader.query('mutation', statement)
        self.assertEqual(connection.statements, [])

    def test_query_failure_is_isolated_and_error_text_is_not_saved(self):
        connection = Connection()
        reader = audit.Reader(connection)
        self.assertEqual(reader.query('failure', 'SELECT failure'), [])
        self.assertEqual(reader.checks['failure']['status'], 'inconclusive')
        self.assertNotIn('sensitive-error-text', str(reader.checks))
        self.assertIn('ROLLBACK TO SAVEPOINT audit_check', connection.statements)
        self.assertEqual(connection.statements[-1], 'RELEASE SAVEPOINT audit_check')

    def test_missing_tables_are_reported_without_querying_them(self):
        connection = Connection()
        reader = audit.Reader(connection)
        reader.check('offers', {'marketplace_offer': ['id']}, 'SELECT id FROM marketplace_offer')
        self.assertEqual(reader.checks['offers']['status'], 'not_applicable_to_schema')
        self.assertEqual(connection.statements, [])

    def test_read_write_transaction_is_refused(self):
        reader = audit.Reader(Connection(read_only='off'))
        with self.assertRaisesRegex(RuntimeError, 'Read-only'):
            reader.run()
        self.assertEqual(list(reader.checks), ['transaction_safety'])

    def test_empty_legacy_schema_is_not_reported_as_clean_data(self):
        reader = audit.Reader(Connection())
        reader.run()
        self.assertEqual(reader.checks['listing_consent']['status'], 'not_applicable_to_schema')
        self.assertEqual(reader.checks['migration_history']['status'], 'not_applicable_to_schema')
        self.assertEqual(reader.checks['local_migration_comparison']['status'], 'inconclusive')

    def test_timeout_budget_marks_checks_not_run(self):
        reader = audit.Reader(Connection())
        reader.started = 0
        with patch.object(audit.time, 'monotonic', return_value=91):
            reader.query('budget', 'SELECT 1')
        self.assertEqual(reader.checks['budget']['status'], 'not_checked')

    def test_railway_wrapper_rejects_non_read_commands(self):
        with patch.object(audit.subprocess, 'run') as run:
            for command in ['deploy', 'migrate', 'set', 'backup_create']:
                with self.assertRaises(ValueError):
                    audit.railway_json(command)
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()

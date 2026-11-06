# Reporting schema expansion

Accounts 0011 is pending and can be corrected before release. Its contact_email
column uses both default='' (Python instances) and db_default='' (persistent
database default). Existing rows receive an empty string; historical ORM workers
that omit the column continue inserting reports. The column remains NOT NULL.
No report rows, categories, access rules or review workflow are rewritten.
See [Django database defaults](https://docs.djangoproject.com/en/6.0/ref/models/fields/#db-default).

The pending graph is accounts 0007 -> 0008 -> 0009 -> 0010 -> 0011, with
learning 0017 -> 0018 also required by accounts 0009. Messaging 0014 -> 0015
is independent. Accounts 0008 adds age fields and guardian authorization/audit
tables and constraints; 0009 adds unique guardian contact/course permissions;
0010 adds Google deletion reauthentication fields. Learning 0018 adds minimum_age;
messaging 0015 adds is_guest and nullable invitation_expires_at. None performs a
data backfill that grants guardian, course, contact or report-review permissions.

This fixes report INSERT compatibility specifically. Other pending NOT NULL
additions (birth_date_source, Google purpose/reauth_auth_hash, course minimum_age,
call participant is_guest) have no persistent database defaults. Their Python
defaults do not protect older workers inserting those respective records. They
need a separate compatibility decision before a mixed-version rollout of those
writers; this change does not claim the whole release is rolling-deploy safe.

PostgreSQL adds this constant-default column without a table rewrite on supported
modern versions, but ALTER TABLE still needs a lock
([PostgreSQL ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html)). Schedule migrations with the
deployment's lock/statement timeout policy. Keep the database default for the whole
old-worker compatibility window; removing it requires a later explicit migration.

Rollback application code while retaining the expanded schema to preserve new
contact addresses and review history. Structural reversal of 0011 removes the
contact column and ReportReviewEvent table, although report rows and preexisting
columns survive. The project's whole-plan guard refuses reversal of populated
created tables. Do not bypass it in deployment. The migration test deliberately
uses Django's base executor on a disposable test database to verify the structural
reverse and reapply path and its data-loss boundary. Reapplying cannot restore
discarded contact addresses or audit history.

If an environment has already recorded the original 0011, editing its source does
not update that database. Such an environment needs an additional forward
AlterField migration to install the database default before old writers resume.
No production migration is performed by this change.

Focused validation (disposable SQLite):

```powershell
.venv/Scripts/python.exe scripts/check_age_accounts.py test accounts.test_reporting_migrations accounts.test_child_safety_reporting core.test_child_safety accounts.test_age_accounts accounts.test_age_feature_safety messaging.test_call_invitations --noinput
.venv/Scripts/python.exe scripts/check_age_accounts.py makemigrations --check --dry-run
```

The same test modules can run with an explicitly isolated PostgreSQL test
configuration. ReportingMigrationTests also inspects the PostgreSQL column
catalog to verify the persistent default and NOT NULL constraint.

Local validation on 2026-11-05: all 70 focused tests passed on both SQLite
(445.616 seconds) and a fresh disposable loopback PostgreSQL cluster
(355.225 seconds). Django system checks, migration drift check and diff whitespace
check passed. PostgreSQL initialization required elevated local execution and a
longer fixture connection timeout on this machine. Production was not accessed.

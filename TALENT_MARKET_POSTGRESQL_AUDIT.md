# Talent Market PostgreSQL audit — 2026-10-18

Scope: PostgreSQL 17.11 in the existing workspace audit cluster on loopback port
55432. All migrations and writes used disposable audit databases. No deployment
or deployed database was accessed. Historical migration files were not changed.

## Upgrade findings and deployment gates

| Migration | Seeded PostgreSQL result | Required before deployment |
| --- | --- | --- |
| marketplace 0001 → 0002, valid existing data | Passed; listing and offer preserved; no marketplace or messaging model/migration drift | Verify target migration history and data before treating this as representative. |
| marketplace 0002, duplicate personal pending offers | Failed creating `market_pending_personal_offer` | Resolve pending duplicates per listing/sender before applying 0002. |
| marketplace 0002, duplicate organization pending offers | Failed creating `market_pending_org_offer` | Resolve pending duplicates per listing/organization, including different recruiters. |
| marketplace 0002, published listing without consent | Failed `market_listing_publication_consent` | Pause affected listings or obtain actual talent consent; do not fabricate consent timestamps. Also preflight all status/decision constraints in 0002. |
| messaging 0005 → 0006, existing conversation and message | Migration succeeds but creates zero participant rows; original talent and organization owner lose room membership | If 0006 is pending, preserve memberships before dropping the old foreign keys. If already applied, audit historical rooms and recover from authoritative records/backups. |
| messaging 0009 → 0010, four legacy calls | Migration succeeds and preserves eight participant rows, but `ACCEPTED` and `REJECTED` remain invalid current call statuses | Review and explicitly map legacy call statuses and participant semantics. Verify pending upgrades and already-migrated data. |
| messaging 0011 → 0012, previously read message | Read timestamp preserved | No blocker reproduced for this fixture. |

The deployed migration history and data have not been inspected, so these are
conditional blockers rather than proof that the target currently contains bad
rows. An empty-database migration run does not establish populated-upgrade safety.
The marketplace constraints use ordinary index/constraint creation, not concurrent
index creation; assess table sizes and schedule writes/locking appropriately.
Historical messaging upgrades discard old foreign keys and do not provide a
validated data-preserving rollback; take a backup and rehearse recovery.

## Concurrency coverage

`marketplace/test_postgresql.py` uses independent thread connections and API
clients, synchronized starts, and bounded database lock/statement timeouts:

- Two simultaneous personal submissions: one 201, one 400, one offer.
- Two recruiters at one organization: one 201, one 400, one offer.
- Talent acceptance versus sender withdrawal: one 200, one 400, consistent consent.
- Message versus final decision: only a pre-decision message can succeed;
  subsequent messages are rejected.

All four passed on PostgreSQL. No production offer code was changed in this audit.

## Test harness correction

The initial 75-test PostgreSQL run had six errors in call cancellation tests.
The async consumer test used Django `TestCase`; Channels connection cleanup closed
the PostgreSQL connection inside the test's outer atomic transaction, causing one
failure and subsequent setup errors. That class now uses `TransactionTestCase`,
allowing actual commits and async connection cleanup without mocking them away.

## Reproduce

Use the repository virtualenv and the existing, running local audit PostgreSQL
cluster. The seeded migration probe verifies the cluster data directory, creates
randomly named databases, and drops only the databases it created:

```powershell
.venv\Scripts\python.exe -u -B scripts/talent_market_postgres_audit.py
$env:AWINLINK_AUDIT_POSTGRES_URL='postgresql://vc_audit@127.0.0.1:55432/awinlink_audit_talent_market'
.venv\Scripts\python.exe -u -B scripts/vc_audit.py test marketplace messaging --noinput --verbosity 1
```

Seeded evidence: `audit-talent-market-postgresql.json`.
Regression output: `audit-talent-market-postgresql-tests.log`.

Final regression result: **79 tests passed on PostgreSQL 17.11**, including all
four concurrency tests (84.828 seconds). The log contains PowerShell's formatting
of Django's normal stderr output; Django's final result is `OK`. The seeded probe
completed all seven scenarios. `git diff --check` passed.

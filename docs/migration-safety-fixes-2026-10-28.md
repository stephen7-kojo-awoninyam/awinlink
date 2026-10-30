# Messaging and migration recovery fixes

Scope: local code and disposable PostgreSQL 17.11 only. No deployment, production queries, production data repair, or provider configuration changes.

## Historical messaging

For databases that have not applied messaging 0006, its conversion now creates participants before removing legacy links. Only the users referenced by the original organization and talent profiles receive membership. Message authors and other organization members receive no inferred access. Duplicate user identities collapse to one participant. Reversal is explicitly irreversible: group membership cannot faithfully reconstruct the removed organization/talent pair.

For databases that already applied the old 0006, removed mappings cannot be reconstructed safely from the current schema. `restore_legacy_conversation_members` validates a reviewed manifest from a restored pre-0006 backup, defaults to dry-run, and requires `--apply` to write. It rejects unknown IDs, duplicate room/user IDs, and nonempty memberships that differ from the manifest. Validation and additions run in one transaction; it never removes existing members or guesses access. Keep the original backup and reviewed manifest as evidence. A source hash records the operator's declared provenance; the command does not prove that a manifest was derived faithfully from that backup.

Manifest format (synthetic IDs):

```json
{"source_backup_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","rooms":[{"conversation_id":1,"user_ids":[2,3]}]}
```

```text
python manage.py restore_legacy_conversation_members reviewed-manifest.json
python manage.py restore_legacy_conversation_members reviewed-manifest.json --apply
```

Review and run against an isolated restored backup first. Reconcile later membership removals, ownership changes and deletion/consent decisions before approving any restored access; old backup membership alone must not override a later revocation. Quiesce membership writers before any separately authorized real repair. A backup manifest must identify the same target database and room/user identities, not merely matching numeric IDs from an unrelated environment. Missing authoritative evidence remains a blocker; this change does not grant access to production rooms.

Messaging 0010 now copies participants on the selected database alias, assigns terminal participant states for terminal legacy calls, and explicitly refuses reversal rather than reintroducing non-null caller/receiver fields without authoritative mappings. A new forward migration, messaging 0014, handles databases that already applied 0010: it retains original ACCEPTED/REJECTED decisions in the non-editable `Call.legacy_status` field and retires those legacy sessions as ENDED. Original call IDs, participants, timestamps and durations remain. Live legacy participants become terminal without inventing timestamps. Modern ACTIVE/RINGING calls are unchanged. No historical accepted session is revived as a live WebRTC call. The provenance migration is intentionally irreversible.

The two historical migration files were changed deliberately for pending upgrade paths. Editing them does not replay their data conversion on databases where they are already recorded as applied; the new forward migration and explicit backup-manifest path address those cases separately. Do not fake migration history to trigger a replay.

Pending call upgrades must continue through messaging 0014 before starting the current application; stopping at historical 0010 alone does not apply the new provenance/status repair.

## Whole-plan rollback preflight

`core` connects a read-only `pre_migrate` handler for the standard Django migrate command. It checks the entire reverse plan before the command executes any migration. It rejects irreversible operations, populated tables that would be dropped by reversing CreateModel, and reversal of organizations 0014 while coach/scout links exist, including REMOVED affiliations. This prevents the observed analytics reversal before a later consent guard fails.

Programmatic migration execution should use `config.migration_safety.SafeMigrationExecutor`; the rehearsal runner does so. Direct third-party use of Django's raw MigrationExecutor does not emit pre_migrate and bypasses this whole-plan check. Per-migration irreversible and organization data guards still apply there. The guard does not promise an atomic multi-migration rollback: lock errors, disk failures, concurrent writes or other later runtime failures can still interrupt a plan. Use one migrator, quiesce incompatible writers, retain verified backups and prefer reviewed forward corrections. A blocked downgrade is intentional data protection, not permission to use --fake.

## Interrupted concurrent indexes

`OnlineIndex` checks PostgreSQL catalogs before reusing or rebuilding a leftover index. Recovery is limited to the plain B-tree indexes used here. It compares table/schema identity, visibility, key columns/order/null placement, default operator classes/collations, uniqueness/exclusion, predicates/expressions, included columns, tablespace/options and constraint/cluster ownership. It refuses active builds or mismatching definitions without deleting them.

- Exact valid/ready/live index: reuse it and finish the unrecorded migration.
- Exact invalid leftover: remove it concurrently, then rebuild concurrently.
- Interrupted reverse: tolerate an already-absent index; verify any remaining definition before removal.
- Conflicting definition or unsupported index form: stop for reviewed recovery; never silently accept a name match.

Migration SQL retains the fixture statement/lock budgets. Database create/drop uses a separate longer lifecycle budget. Concurrent DDL still requires a non-atomic migration and a single migration runner. PostgreSQL documents that [IF NOT EXISTS does not verify index equivalence, and failed concurrent builds can leave invalid indexes](https://www.postgresql.org/docs/17/sql-createindex.html); this implementation validates definitions rather than relying on that clause.

## Validation

The earlier [rehearsal report](populated-postgresql-migration-rehearsal-2026-10-28.md) remains a historical record of the reproduced failures before these fixes.

- Current populated PostgreSQL upgrade: **16 migrations passed**, all 129 original rows/field values preserved across 143 pre-existing tables. Catalog: 263 foreign keys, no invalid indexes or unvalidated constraints.
- Backup restore: original rows and migration recorder fingerprint matched exactly; restored copy also passed all 16 migrations. The coach/scout rollback guard retained all 134 rows and reversed **zero** earlier migrations, including analytics 0005.
- Standalone index interruption/retry: plain retry succeeded, all 53 original fixture rows preserved, no invalid indexes or unvalidated constraints. No manual index removal was needed.
- Targeted PostgreSQL index test: passed real canceled-build recovery, interrupted forward/reverse retries, wrong definition/order/predicate/include refusal and descending-index reuse.
- Final focused PostgreSQL suite: **all seven tests passed, no skips**, in 83.732 seconds. Covers pending historical conversion, already-applied call repair with modern ACTIVE preservation, manifest dry-run/apply/idempotency/conflict/invalid-ID handling, whole-plan command rollback protection, and index recovery. Evidence: `.audit-migration-safety-complete.log` and `.audit-migration-rehearsal/6fc2430f5c184d619f95cc3c2c9a5e24/report.json`; exit zero, no owned databases left. The log's Django "Preserving test database" line refers only to delegating deletion to the outer owning context; that context successfully dropped it.
- Broader regressions: **363 run, 361 passed, two Redis-only skips**, no errors/failures. Migration graph had no conflicts; makemigrations --check reported no changes. Evidence: `.audit-migration-safety-broader.log`.

Ignored local evidence: `.audit-migration-rehearsal/151db0ca18c740fea9759ecb3db3c5e7/report.json` (populated/restore/guard), `17178233807b49c6b4cb3482f7978d7e/report.json` (index retry), and `cc68c8ae212d45b59731294aebcb3312/report.json` (targeted index test). These runs each finished with no owned databases left.

Exploratory runs exposed and corrected both implementation and test-harness issues. The index matcher needed PostgreSQL sort flags separately from column labels. Fixtures initially attempted to reverse deliberately irreversible messaging migrations and omitted a required synthetic course category. Historical scenarios now start in their own verified disposable databases. Slow Windows checkpoints also exceeded Django's separate teardown timeout; the runner now keeps the fresh test database only until its owning outer context drops it using the longer lifecycle budget. Migration statement/lock limits remain unchanged. These exploratory failures remain in local logs; they are not presented as passing test runs.

Reproduce locally with the repository virtualenv and verified workspace cluster:

```text
.venv/Scripts/python.exe -u -B scripts/rehearse_populated_migrations.py --safety-tests-only
.venv/Scripts/python.exe -u -B scripts/rehearse_populated_migrations.py --populated-only
.venv/Scripts/python.exe -u -B scripts/rehearse_populated_migrations.py --index-recovery-only
.venv/Scripts/python.exe -u -B scripts/audit_production_readiness_local.py
```

Final cleanup verification found no databases remaining in either invocation namespace (`awinlink_rehearsal_` or `awinlink_safety_`) and no other clients. The local workspace cluster was shut down cleanly, restoring its original stopped state. Evidence: `.audit-migration-rehearsal/safety-fixes-cleanup-verification.json`. Syntax, whitespace and scoped diff checks passed. No deployment occurred.

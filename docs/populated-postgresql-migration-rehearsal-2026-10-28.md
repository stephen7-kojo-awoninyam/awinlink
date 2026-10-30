# Populated PostgreSQL migration rehearsal

Date: 2026-10-28. **Current clean-fixture upgrade and synthetic backup/restore passed. Production migration approval remains blocked by the conditional historical hazards and recovery gates below.**

All writes used newly created UUID-named databases on PostgreSQL 17.11 at loopback port 55432. The runner checked `SHOW data_directory` against the workspace's `.audit-vc-tools/postgres-data` before creating databases. It did not read DATABASE_URL/dotenv, query production, change Railway configuration, deploy, or modify application migration files. Fixture data and documents are synthetic; document storage paths were checked as database values, not uploaded or fetched.

## Results

| Scenario | Observed result | Release implication |
| --- | --- | --- |
| Current populated baseline to all current leaf migrations | 15 migration steps passed; all 129 original rows/field values preserved across 143 pre-existing tables, including empty tables. Catalog: 263 foreign keys, no invalid indexes, no unvalidated constraints. | The tested clean baseline can upgrade. This does not establish that production has the same starting schema/data. |
| Restore pre-upgrade custom dump, then upgrade | Restored rows and migration history matched the original fingerprint exactly. The restored copy also completed the 15-step upgrade and preserved all 129 original rows. | Demonstrates a working local logical backup/restore path with these synthetic fixtures, not a verified production backup. |
| marketplace 0001 to 0002, clean populated rows | Listing and offer retained. | Positive control passed. |
| marketplace 0002, duplicate personal/organization pending offers | Upgrade rejected each duplicate fixture; failed migration preserved original rows. | Conditional blocker: reconcile duplicate actionable offers before adding uniqueness constraints. |
| marketplace 0002, published listing without consent | Upgrade rejected the fixture; original rows preserved. | Conditional blocker: establish legitimate consent or an approved paused state; never invent consent evidence. |
| messaging 0005 to 0006 | Message survived, but zero participant rows were created for the two original participants; legacy relationship columns were removed. Reverse migration failed with IntegrityError. The failed reverse left upgraded rows intact. | Data/access integrity blocker if this historical path is pending, or if affected rooms were previously upgraded without repair. |
| messaging 0009 to 0010 | Four calls and eight participant rows survived; ACCEPTED and REJECTED remained outside current call status choices. Reverse migration failed while restoring non-null receiver/caller columns. | Conditional lifecycle and rollback blocker; require evidence-based status reconciliation and authoritative participant history. |
| messaging 0011 to 0012 | Read timestamp/history preserved. | Positive control passed. |
| learning category seed forward/reverse | All 53 original rows preserved, including 50 lessons, the course and custom Sports description. Four categories remained after reverse. | Reverse is deliberately a no-op for category data, protecting course references; it does not restore an identical pre-seed dataset. |
| Interrupted learning 0015 concurrent indexes | Injected failure before the second index left `learning_lesson_page_idx` committed, but no migration recorder entry. Plain retry failed with SQLSTATE 42P07 (existing relation). Removing only this invocation's verified leftover index in the disposable DB allowed completion; original rows remained and indexes/constraints were valid. | **Recovery blocker:** an interrupted non-atomic migration is not safely resumable by blindly rerunning migrate. Prepare and review catalog-based recovery before release. |
| Reverse organizations 0014 after retaining a removed coach affiliation | IrreversibleError correctly protected coach consent/history links; all 134 rows remained. However, dependent analytics 0005 had already been reversed before the guard raised. | **Rollback blocker:** the guard protects data, but the overall reverse plan is not all-or-nothing. A failed rollback can still change other migrations/indexes. |

The current baseline was built from the graph before organizations 0014, learning 0014, messaging 0013, recommendations 0003, talents 0016 and media_erasure 0001, excluding their descendants. It includes modern organization agreements, memberships and marketplace bookings. The fixture contains 100 messages, call participants/history, private profile/verification/lesson path references, course progress/enrollment, an active agreement with matching consent digests, a confirmed roster affiliation, and an accepted marketplace offer/booking/event. Comparisons retain each original column and row identity while allowing legitimate added columns and category seed rows.

The 15 forward steps cover talents 0016; organizations 0014; analytics 0005; learning 0014-0015; media_erasure 0001-0007; messaging 0013; recommendations 0003-0004. Fresh model tables were empty at upgrade time: this does not prove retention of data created in those new tables after release.

## Blockers and rollback decisions

1. **Inspect the real target before approving migrations.** Its migration recorder, physical schema, constraint/index validity, duplicates, consent, memberships and call statuses remain unknown. The historical failures above are reproduced fixture cases, not evidence that production currently contains those rows. Do not use --fake or edit already-applied migration files to hide divergence.
2. **Resolve historical data hazards with authoritative evidence.** Preserve old conversation ownership/member mappings before destructive column removal. Current organization membership or message authorship alone is not permission to re-add someone to a private conversation. Preserve original call statuses and decision timestamps in a reviewed repair manifest. Duplicate offers may contain distinct terms; keep history and obtain a decision about which remains actionable.
3. **Treat concurrent index failures as partial DDL.** Inspect migration history and exact index definitions/readiness/validity together. A valid committed index can still conflict with an unrecorded migration, so checking only invalid indexes is insufficient. The fixture cleanup is not a production repair instruction or permission to drop an index. Index repair/retry must be scoped, reviewed and separately authorized.
4. **Do not promise a universal reverse migration.** The legacy conversation/call reverses failed; organization 0014 is intentionally blocked once coach/scout links exist; another migration may reverse before that guard runs. New-table reverses can drop post-release records such as discovery preferences/alerts and media-erasure jobs/legal holds. That latter loss risk follows from schema operations and was not exercised with real retention data. Prefer a reviewed forward correction where appropriate; otherwise use an approved restore/cutover plan that accounts for writes after the backup.
5. **Validate production permissions and operating conditions.** The fixture role can create databases/extensions. Production still needs reviewed PostgreSQL version/role privileges, including btree_gist where booking overlap protection requires it. The small fixture does not establish production DDL lock duration, disk/WAL headroom, index build resource use, write load or maintenance-window length. Keep ASGI workers and background jobs compatible with the migration order.

## Backup requirements before any production migration

- Verify a fresh completed, retained production backup and its actual recoverable timestamp. Define the required RPO/RTO, retention, owner and recovery decision authority. Earlier metadata recorded no backup schedule/PITR; this rehearsal did not recheck Railway and does not establish today's coverage.
- Use a compatible PostgreSQL client and a full custom-format logical archive where that is the chosen recovery method. Capture checksum, archive inventory, server/client versions, migration history and required extensions. Keep credentials out of arguments, source control and shared logs; encrypt/restrict production archives and store a recoverable copy offsite.
- Rehearse restoration of that approved backup into a separate, isolated target, then validate schema, rows, relationships, consent/history, sequences and application reads. The local synthetic dump restored here omits ownership/ACL restoration (`--no-owner --no-acl`); production roles/grants and cluster-level objects require their own inventory and recovery steps.
- Back up/inventory external media and relevant provider identities, private delivery types, legal holds, secrets/configuration and application release artifacts separately. A PostgreSQL dump does not contain Cloudinary files or establish CDN revocation.
- Preserve a pre-migration backup, and plan for post-backup writes/new feature records before choosing rollback. Do not overwrite a running production database with this fixture archive or restore workflow. Provisioning backups, PITR, restore services or production cutover remains a separate authorized change.

## Reproduce and evidence

Use `scripts/rehearse_populated_migrations.py` with the repository virtualenv and the verified existing workspace cluster. It never accepts an arbitrary host/DSN. Expected hazardous fixtures are reported as findings; a successful harness execution is not a release approval.

```text
.venv/Scripts/python.exe -u -B scripts/rehearse_populated_migrations.py
.venv/Scripts/python.exe -u -B scripts/rehearse_populated_migrations.py --populated-only
.venv/Scripts/python.exe -u -B scripts/rehearse_populated_migrations.py --index-recovery-only
.venv/Scripts/python.exe -u -B scripts/rehearse_populated_migrations.py --agreement-tests-only
```

Evidence under ignored `.audit-migration-rehearsal/`:

- `919c72b0b3394118b475eec89f445fb7/report.json`: historical populated probes and initial PostgreSQL regression results: 48 run, 47 passed, one historical-schema test errored, no skips. Its disposable databases were removed.
- `a5829108c7ce444c87a7da80af1b3f2a/report.json`: successful current upgrade, restore and coach rollback guard.
- `a52ca16e35d2470892ba068879a2c46d/report.json`: category reversal and concurrent index interruption/recovery.
- Synthetic custom archive: `a5829108c7ce444c87a7da80af1b3f2a/synthetic-before-upgrade.dump`, 598,697 bytes; SHA-256 `f4aa6d0d15de3a43088d9b51a51002854b66aed2ce99dc02e673f10269ee14f0`.

An initial synthetic agreement fixture passed its amount as a string to a Decimal-formatting hash function; refreshing typed database values fixed that fixture. It was not a migration defect. Windows checkpoint latency also exceeded the original fixture cleanup timeout; cleanup was tracked separately and the runner now gives database lifecycle operations a distinct 15-minute budget (the completed probe still used the earlier three-minute budget). Migration statements retain a 30-second statement budget and two-second lock budget; existing concurrency tests also use their own timeouts. The initial cleanup timeouts were resolved by a separate retry after verifying the exact four owned fixture names and absence of active connections; all four were dropped. Evidence: .audit-migration-rehearsal/cleanup-retry.json. Original reports retain their timeout results rather than overwriting that history.

References: PostgreSQL documents [custom dumps and their database-only scope](https://www.postgresql.org/docs/17/app-pgdump.html), [restore behavior](https://www.postgresql.org/docs/17/app-pgrestore.html), and [concurrent index build restrictions/failure states](https://www.postgresql.org/docs/17/sql-createindex.html). See also the repository's production backup/restore plan and prior PostgreSQL audit for operator-specific gates.

## Regression fixture correction

The initial error was in `AgreementPostgresTests.test_0013_preserves_existing_roster_and_history_without_inventing_agreements`: after reversing to organizations 0012, it queried current runtime models that require coach/scout columns introduced by 0014. PostgreSQL correctly rejected the absent `coach_id` column. The test now reads the historical schema with matching historical models and compares its original columns before reversal, at 0012, after the explicit 0013 transition, and again at current leaves. It still asserts that no agreements or consents were invented. Application migration files, consent checks and runtime behavior were unchanged.

After that fixture correction, **all 10 agreement PostgreSQL tests passed, with no skips**, including migration preservation, consent/revision races, account safety locks, withdrawals, roster removal and ending decisions. Evidence: `36fa084105844267a1e1736bebd9eca7/report.json` and `.audit-migration-agreement-final.log`; exit status zero and no owned databases left. The other 38 tests passed in the earlier broad run; the full 48-test suite was not repeated after this test-only correction. Python syntax and scoped diff checks passed. All prior rehearsal databases, including the four timeout leftovers, were confirmed absent.

After confirming no other database clients were connected, the verified workspace cluster was shut down cleanly, restoring its original stopped state. Synthetic dump/report artifacts remain locally ignored; no production systems were changed or deployed.

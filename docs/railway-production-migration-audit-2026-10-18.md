# Railway production migration audit preparation

Date: 2026-10-18. Target verified through Railway's read-only status and resolved
service variables: project **awinlink**, environment **production**, Postgres
service `a80a9307-b793-4089-9d1e-59d87bb046b0`. The application's resolved
`DATABASE_URL` matches that service's private database identity.

**Decision: do not approve production migration yet. No production SQL query has
been executed. No rows, schemas, variables, access keys, backups, networking, or
deployments were changed. No full production data export was taken.**

## Verified Railway findings

At 2026-10-18 18:54:46 UTC, read-only Railway metadata reported:

| Item | Observed result |
| --- | --- |
| PITR | `enabled: false`, `bucketWired: false` |
| Existing backups returned by Railway | Empty list |
| Configured backup schedules | Empty list |
| Public database connection URL | Not exposed by the existing service variables |
| Existing application SSH route | CLI refused: no SSH keys in the agent or default SSH directory |

This establishes no verified Railway backup coverage. It does not rule out
separately managed offsite backups, which were not available to inspect.
Sanitized evidence is stored locally in
`.audit-production-migration/backup-metadata.json`. Credentials were handled
only in memory and were not printed or written to reports.

## Production data checks: blocked, not clean

| Check | Current production result | What the prepared checker examines |
| --- | --- | --- |
| Migration history | Not verified | All `django_migrations` rows; compare with local migration filenames; flag pending and unknown migrations. |
| Physical schema | Not verified | Available tables/columns, constraint definitions and validation, index definitions/readiness/validity. |
| Pending offer duplicates | Not verified | Personal groups by listing/sender; organization groups by listing/organization across recruiters; counts and bounded ID samples. |
| Listing consent | Not verified | Published rows without consent, invalid statuses, future consent timestamps. |
| Offer consent and decisions | Not verified | Pending/final timestamps and acceptance consent matching the proposed database constraints. |
| Conversation memberships | Not verified | Zero-member rooms, direct rooms with fewer than two members, historical senders/current creators absent from current membership, surviving legacy foreign keys. |
| Calls | Not verified | Legacy `ACCEPTED`/`REJECTED`, other statuses outside current choices, active calls with end timestamps, missing initiators/participants. |

Missing tables are reported explicitly; they are never interpreted as zero bad
rows. An unavailable query or timeout remains inconclusive. A migration recorder
entry alone does not prove the schema or backfill is correct. Filename comparison
is not a dependency-graph verification or a substitute for a restored-copy rehearsal.

## Prepared read-only checker

`scripts/railway_migration_audit.py` imports no Django application code and invokes
no management commands. Its Railway wrapper permits only status and variable
reads; the SSH route runs the same fixed SELECT queries inside the existing app
container using `python -B`, without writing a remote script or bytecode.

Database safeguards:

- Read-only mode is enabled in connection startup options, before the first query.
- Explicit `REPEATABLE READ, READ ONLY` session; verified with `current_setting`.
- 15-second statement timeout, 1-second lock timeout, 30-second idle transaction
  timeout, and a 90-second total query budget (a final in-flight query can add up
  to 15 seconds). Queries use ordinary reads, not `FOR UPDATE`.
- Each query has a savepoint so an error is recorded without losing the snapshot.
- Transaction always rolls back and closes; no DDL, DML, temporary tables,
  `EXPLAIN ANALYZE`, migrations, tests, or maintenance commands run on production.
- Report contains counts, internal IDs, status distributions, catalog metadata,
  and migration timestamps; no messages, offer terms, emails, names, or passwords.
- Seven offline safety tests pass. They verify refusal of mutation statements,
  read-only enforcement, missing-schema handling, bounded checks, savepoint error
  isolation, sensitive-error suppression, and the Railway command allowlist.

To resume, use an **existing authorized** Railway SSH identity or an operator's
already working access route. Do not generate/register keys, enable a proxy, or
alter production settings as part of this audit. Example with an existing key:

```powershell
.venv\Scripts\python.exe -u -B scripts/railway_migration_audit.py --railway-production-ssh --identity-file C:\path\to\existing_authorized_key --output .audit-production-migration/read-only-findings.json
```

If an existing public endpoint becomes available independently, the alternative
is `--railway-production`. It requires TLS, checks the project/environment/service
and application database reference, and refuses to create a public endpoint.
The existing CLI must already be authenticated. Keep DSNs and passwords out of
chat, shell history, command arguments, Git, and shared reports.

An operator can begin with this catalog-only SQL through their existing client:

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '1s';
SET LOCAL idle_in_transaction_session_timeout = '30s';
SELECT current_database(), current_setting('transaction_read_only'),
       current_setting('transaction_isolation');
SELECT to_regclass('public.django_migrations') AS migration_table,
       to_regclass('public.marketplace_listing') AS listings,
       to_regclass('public.marketplace_offer') AS offers,
       to_regclass('public.messaging_conversationparticipant') AS memberships,
       to_regclass('public.messaging_call') AS calls;
ROLLBACK;
```

The adaptive checker contains the remaining SELECTs and checks columns before
querying tables, making it safer than pasting current-schema queries into an
unknown historical production schema. Reads can still consume resources and
briefly contend with DDL; run during a quiet period and preserve the timeouts.

## Proposed non-destructive repairs — not executed

First rehearse on an isolated restored copy. Produce a reviewed before/after
manifest containing exact IDs, original values, evidence, and the approved
result. Preserve messages, terms, participants and decision history. Use a new,
versioned, idempotent repair where needed; do not rewrite applied migrations or
use `--fake` to bypass constraints.

1. **Duplicate pending offers:** compare terms, organization and sender for every
   group. Ask the authorized sender/organization and talent to identify the offer
   that should remain actionable. Withdraw redundant pending offers through an
   approved workflow and retain every offer and deal message. Do not delete rows
   or automatically pick the oldest when terms differ. Quiesce offer writes for
   the later repair/constraint window so new duplicates cannot enter the gap.
2. **Missing listing consent:** propose pausing affected published listings until
   the talent provides explicit consent to the actual details. Preserve existing
   contents and legitimate evidence. Never fabricate publication or acceptance
   timestamps. Inconsistent accepted offers need evidence review, not automatic
   acceptance or a replacement consent timestamp.
3. **Conversation memberships:** zero/one-member rooms and absent historical
   senders are review signals, not proof of who may access a room. Users may have
   legitimately left or been removed. Before pending messaging `0006`, preserve
   the authoritative old talent/organization-owner mappings and membership
   evidence before their columns disappear. If already applied, use a verified
   pre-migration backup or audit record to recover only proven memberships.
   Message authorship, platform-admin status, and current organization membership
   do not establish permission to re-add someone. Do not grant whole organizations
   access or expose message bodies while investigating.
4. **Legacy call statuses:** preserve original values in the repair manifest.
   Review `ACCEPTED` calls against answer/end evidence; use `ENDED` when a genuine
   end is recorded and `ACTIVE` only when the call is verifiably live. Quarantine
   ambiguous history for review rather than reviving old calls. A rejected call
   can be mapped to the current terminal lifecycle only with consistent receiver
   `REJECTED` and caller terminal states, based on original participant evidence.
   Never invent end times, durations or participant identities.

The local seeded audit reproduced marketplace `0002` rejecting duplicates and
missing publication consent, messaging `0006` losing old membership links, and
messaging `0010` retaining legacy call choices. Those results identify checks to
run; they do not establish which affected rows exist in production.

## Backup and recovery proposal — not executed

Before any production repair or migration:

1. Verify any existing offsite backup, if the operator has one: scope, timestamp,
   encryption/access, checksum, retention and successful restore evidence.
2. Plan a fresh full logical `pg_dump --format=custom --no-owner` using an existing
   approved connection, a client compatible with the actual production server
   version, and secret injection outside command arguments. Store it encrypted
   offsite. Include `django_migrations` and all related account, talent,
   organization, marketplace, messaging and notification tables; a full dump
   avoids missing foreign-key dependencies. Inventory required roles/extensions
   separately without exporting account secrets into shared artifacts.
3. Inspect the archive with `pg_restore --list`, calculate a SHA-256 checksum, then
   restore it into a separate isolated PostgreSQL instance. Listing an archive
   alone does not prove it restores. Rehearse both upgrade and data checks there;
   compare exact counts and memberships, index/constraint validity, migration
   history, consent integrity and call history. Measure recovery time and data age.
   Preserve access to external media and deployment configuration separately.
4. Schedule a Railway pre-migration snapshot and backup schedule as a separately
   authorized production change. Verify completed status and the recoverable
   timestamp before relying on them. No backup was created during this audit.
5. Consider PITR as a separately authorized change. Railway enabling PITR changes
   variables and redeploys the database; it must not be enabled under this task's
   no-change instruction. Coverage begins after the initial base backup and is
   not retroactive. Check actual archive health and restore range afterward.
6. Define a write-quiescence/cutover window before later changes and an application
   compatibility plan. Prefer selective, reviewed repairs from a restored copy
   over overwriting production. Whole-database rollback can discard later valid
   writes. Never restore a volume backup over the running production database as
   a rehearsal. PITR recovery provisions a sibling service; cutover remains a
   separately authorized action.

Railway references: [Postgres backup/restore guide](https://docs.railway.com/guides/postgres-backups-restores),
[PITR behavior and limitations](https://docs.railway.com/volumes/point-in-time-recovery).

## Required gates

- Existing authorized database/SSH access for the blocked read-only checks.
- Production migration history, schema and all data findings actually reviewed.
- Verified recoverable backup and isolated restore rehearsal.
- Approved repair manifests and privacy checks where issues are found.
- Rehearsed populated upgrades, bounded locking plan, and a compatible recovery
  strategy before any production migration is considered.

No deployment or production modification is authorized by this report.

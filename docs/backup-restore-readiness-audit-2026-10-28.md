# Production backup and restore readiness audit

Date: 2026-10-28. **Production recovery readiness is unproven; do not clear the backup/recovery release gate.** This assessment uses repository code, historical reports and existing synthetic rehearsal artifacts only. No Railway account, production database, Redis, provider assets, credentials or backups were accessed. No services were started, production checks executed, backups created, restores run or deployments performed. Public provider documentation was consulted.

## Evidence and blockers

| Priority | Finding | Evidence required to clear it |
| --- | --- | --- |
| P0 | No currently verified recoverable production backup. The October 18 metadata report and October 20 record reported no volume backups/schedules and PITR disabled. October 28 metadata attempts were inconclusive. These are historical observations, not today's account state. | Authorized operator evidence of a completed, retained backup for the correct database, actual recoverable timestamp and usable recovery credentials. |
| P0 | No successful restore of an actual production backup is documented. | Isolated restore, integrity/security checks, approved recovery point and measured end-to-end recovery time. |
| P0 | RPO, RTO, accountable owner and incident decision authority are not established by available evidence. | Named owner and alternate, approved maximum data loss/outage, retention policy and dated recovery sign-off. Do not invent objectives from a script threshold. |
| P1 | Schedule, failure alerts, offsite independence, encryption and key recovery are not verified. | Sanitized scheduling/retention evidence, monitored last success and failed/missed-job alerts, access-controlled independent copy and a demonstrated decryption/access path. Repository absence is not proof that an external backup job does not exist. |
| P1 | Database recovery alone does not cover private media, application/configuration identity, Redis security state or external side effects. | The dependency inventory and reconciliation checks below, with owners and recovery order. |
| P1 | The older Phase 2 drill conflated volume restore with sibling creation. | Correct method/target reviewed before any operation. The linked plan has been corrected locally. |

Historical sources: [production migration audit](railway-production-migration-audit-2026-10-18.md), [Phase 1 backup section](security-phase1.md#backup-readiness-blocked), [production readiness](production-readiness-audit-2026-10-28.md). The local `db_backup_before_migrations.sqlite3` file is not evidence of a production PostgreSQL backup; its contents were not inspected. The queried dump/backup filename patterns had no tracked matches; that narrow Git check is not a complete secrets/history scan.

## What the local evidence proves

The [migration safety rehearsal](migration-safety-fixes-2026-10-28.md) completed a populated PostgreSQL 17.11 upgrade and a synthetic custom-archive restore. Both copies applied 16 migrations and preserved 129 original rows/field values. The restore matched the original row and migration-recorder fingerprint. Catalog checks found 263 foreign keys, no invalid indexes and no unvalidated constraints. Whole-plan rollback protection and interrupted-index recovery passed separate fixture tests. All disposable databases were removed and the fixture cluster was stopped.

This audit rechecked only that existing synthetic archive offline: 598,768 bytes, SHA-256 `7c3f689e443dadf80fcac888a3546bad68a10a4ef3bc3392870bc0de59bfbfa0`, 1,354 archive entries including 143 sequence-set entries. `pg_restore --list` requested no database connection. Inventory and checksum establish artifact consistency, not successful sequence advancement or production completeness. Post-restore sequence/write behavior, actual production roles/grants, full-scale runtime/performance and external recovery remain unverified.

Archive: `.audit-migration-rehearsal/151db0ca18c740fea9759ecb3db3c5e7/synthetic-before-upgrade.dump`. Prior drill report: the sibling `report.json`. These are ignored synthetic local artifacts, not a production backup service or retained offsite copy.

## Existing checker assessment

`scripts/check_backup_readiness.py` is an account-accessing tool, **not an offline validator**. Its main path invokes Railway status/API/variable reads, including resolving production identity and database references in memory. It runs no SQL and performs no mutations, but running it would violate this task's no-production-access boundary. It was not run.

Its fixed query requests backup IDs/creation/expiry and schedule kind/retention. It suppresses sensitive CLI errors and never returns READY merely because metadata exists. Limitations:

- Creation/expiry timestamps do not establish backup completion, consistency, accessibility, coverage or successful decryption/restore. No completion/status field is requested.
- A fixed 24-hour freshness check is not an approved RPO; creation time need not equal the latest recoverable transaction time.
- A nonempty schedule list is not validation of frequency, retention, failure monitoring or execution history. Missing expiry does not independently prove unlimited retention.
- PITR status and bucket wiring do not prove a usable base backup, continuous WAL coverage, recoverable time range or successful timestamp recovery.
- No metadata result proves external media backup, roles/grants, independent offsite recovery, RTO or application correctness.

All **12 offline tests** in `scripts.test_backup_readiness` and `scripts.test_railway_migration_audit` passed during this audit. Unmocked subprocess calls, PostgreSQL connections and socket connections were explicitly blocked. This verifies the exercised checker logic, not any production fact. No checker/runtime code was changed for this audit.

## Safe verification plan

Stages 1–4 are prepared for a later, explicitly authorized operator. They were not executed. Stop on unknown identity, incomplete evidence, unexpected network access or an unapproved target; mark the result INCONCLUSIVE rather than clean.

### 0. Offline preparation — completed within this task

- Review historical evidence, scripts and provider workflow; record unknowns separately from observed failures.
- Run mocked checker tests; inspect only the known synthetic archive inventory/checksum.
- Prepare the evidence record and recovery checklist below. Do not read `.env`, secret stores or provider account state to fill unknown fields.

### 1. Account metadata verification — later authorization required

1. Use the operator's existing approved access route. Verify project, environment, database service, attached volume and application reference without publishing IDs/DSNs/credentials. Do not enable a proxy, tunnel, SSH key or PITR merely to obtain evidence.
2. Obtain sanitized backup type, completion outcome, recovery timestamp, expiry/retention and last successful scheduled execution. Verify alert delivery and the human escalation path for missed/failed backups.
3. If PITR is part of the agreed RPO, verify base-backup completion, WAL continuity and earliest/latest recoverable timestamps. An enabled flag alone does not pass. If snapshots satisfy the approved RPO, record that decision; PITR is not presumed mandatory.
4. Verify independent-copy location/failure domain, encryption, deletion protection as required by policy, least-privilege access and emergency key access. Keep actual keys and signed backup URLs outside repository/logs.

### 2. Choose the restore route and prove isolation — later authorization required

Railway currently documents volume restores against the existing service, while PITR creates a sibling beside the source. Neither is automatically a separate isolated test environment. A production volume restore is excluded from a rehearsal. An independently provisioned non-production target plus an approved existing logical archive is the default drill route here. Confirm current behavior before use. [Railway restore methods](https://docs.railway.com/guides/postgres-backups-restores).

- Record source backup identity and an independently verified target identity; require that the target is new/empty and not referenced by production apps. An empty database name on the same production server is insufficient isolation for this plan.
- Deny access to production PostgreSQL/Redis/media APIs and outbound email, push, payment callbacks and TURN-provider mutations from the drill. Disable workers, cron, webhooks and erasure processing before launching any restored application. Use isolated Redis and nondelivery/mock providers; copied settings are not safe defaults.
- Prefer the backup's matching application release first. Record PostgreSQL/client versions, required extensions (including `btree_gist` when applicable), role capabilities and available disk/WAL capacity. Then separately rehearse upgrading to the candidate release.
- Use synthetic data when possible. Actual production archives require approved access, encrypted restricted storage, retention/cleanup ownership and appropriately protected test infrastructure. A localhost address alone does not prove isolation if it is a production tunnel.

### 3. Restore and validate — isolated target only, later authorization required

1. Verify archive checksum against trusted backup evidence, completeness and provenance; inspect its inventory and review restore content where source trust is uncertain. A checksum alone is not authenticity or recoverability.
2. Restore only into the verified empty target with an approved target-only connection profile. Keep credentials out of CLI arguments/history. Use `pg_restore --exit-on-error`; do not use `--clean`, `--create`, trigger disabling or source connection strings as convenience shortcuts. An error leaves the target unapproved; inspect or discard/recreate only the verified disposable target, never continue as if complete. PostgreSQL documents that restore can execute source-defined code and that errors otherwise need not stop processing. [Restore behavior](https://www.postgresql.org/docs/17/app-pgrestore.html).
3. The fixture's `--no-owner --no-acl` intentionally omitted ownership/grants. Recover and verify production-equivalent roles/grants/extensions through a separately reviewed inventory, without importing production login secrets into the drill. Database dumps do not include all cluster-global objects. [Dump scope](https://www.postgresql.org/docs/17/app-pgdump.html).
4. Compare against evidence captured at the backup's consistent recovery point, not current live counts: migration recorder and physical schema, required tables/columns, exact critical row counts and protected fingerprints, FK/check validation, index definitions/readiness/validity, and sequence/identity state. Estimated `n_live_tup` counts are triage only. Missing/unreadable tables are unknowns, not zero bad rows.
5. On the isolated target, perform controlled writes to exercise generated IDs, constraints and representative transactions. Sequence increments may survive transaction rollback; perform these probes only in the disposable copy. Verify memberships/consent, call history, agreements, bookings, refund/idempotency records and erasure/legal-hold state without printing private content.
6. Run isolated application/security checks: unauthenticated/private-media denial, removed-member denial, auth revocation, Redis outage fail-closed behavior, and representative authorized reads. Rehearse candidate migrations with one migrator. A successful SQL restore is not application acceptance.
7. Record actual recovery point and time from incident decision through infrastructure, artifact retrieval/decryption, restore, validation and service readiness. Tiny fixture timings do not establish a production RTO. Clean up only verified drill resources; record archive retention and cleanup outcome.

### 4. Acceptance gate

Pass only when the owner signs off the agreed RPO/RTO, a usable retained backup plus repeatable schedule/alerts, tested isolated restoration, role/security/integrity validation, independent-copy/key recovery, external dependency reconciliation and cleanup evidence. Unknown or failed items remain blockers. This audit does not authorize production cutover.

## Recovery dependencies

| Component | Recovery requirement |
| --- | --- |
| PostgreSQL | Backup/recovery point, complete schema/data, migrations, roles/grants/extensions, sequences and integrity checks. Keep the exact compatible application release available. |
| Private Cloudinary/local media and CDN | Separately inventory assets, immutable provider identity, delivery/access type, legal holds and backup/version availability. Database paths do not contain file bytes. Test privacy with controlled fixtures; do not request production assets during this audit. |
| Erasure/retention and access history | Reconcile deletions, holds and revoked memberships that occurred after the restore point. Keep erasure workers paused until stale jobs/holds and restored references are reviewed; a restore must not resurrect access or trigger inappropriate deletion. |
| Redis/Channels/security counters | Inventory actual persistence and uses. Do not assume a Django cache backup equals durable business state. Rebuild transient signaling; clients reconnect and active calls may be interrupted. Restore required security/rate-limit service availability before reopening auth; do not fail open or reuse production Redis in a drill. |
| Sessions/JWT/password changes | Assess restored accounts, password/reset state and revocation/blacklist history against post-backup changes. Approve an explicit session/token invalidation strategy before traffic; never silently revalidate previously revoked credentials. |
| Secrets/configuration and release artifacts | Recover approved signing/encryption/provider identities from the secret manager, with an alternate authorized operator; do not store their values in evidence. Verify private routing, environment references and production security settings. Credential rotation, if needed, is a separate coordinated recovery decision. |
| Payments, refunds, bookings, notifications | Reconcile external payment/refund/webhook outcomes and idempotency records after the recovery point before replay. Do not blindly repeat charges/refunds or deliveries. Preserve authoritative provider evidence and business decisions. |

## Incident recovery checklist — prepared, not executed

- [ ] Name incident commander, database operator, security/data owner and approver; record UTC timeline, scope, cause and recovery objective.
- [ ] Contain incompatible writes and automatic jobs; preserve original database/logs and recovery evidence. Do not delete the source volume or overwrite the only usable backup.
- [ ] Select a known-good recovery point before corruption and quantify the data-loss interval. Verify backup completion, retention, access/decryption and method/target identity.
- [ ] Provision an isolated replacement; restore and validate as above. Preserve the original environment for reconciliation and investigation.
- [ ] Check application release/schema compatibility. Use forward corrections where appropriate; do not bypass irreversible guards, fake migrations, drop mismatching indexes or fabricate consent/membership history.
- [ ] Reconcile post-backup payments/refunds, privacy revocations, deletions/legal holds, password/token changes and business writes. Obtain decisions for irrecoverable gaps.
- [ ] Establish replacement backup/alert coverage, Redis/security availability and external provider configuration before accepting traffic.
- [ ] Obtain separate explicit production-cutover approval against the concrete validated target. Record connection/routing changes, worker restart order, validation, owners and rollback criteria. Prevent split-brain; never switch back to a stale writable source without reconciling new writes.
- [ ] Monitor error rates, data integrity, auth/private access, payments and jobs. Close the incident only after RPO/RTO measurement, data-owner sign-off, evidence retention and verified cleanup.

## Sanitized evidence record

Keep sensitive raw evidence in the approved restricted system; fill this record with references and outcomes only.

| Field | Current record / required entry |
| --- | --- |
| Audit scope | Offline repository/evidence review; production not accessed |
| Owner / alternate / approver | Not verified — required |
| Approved RPO / RTO / retention | Not verified — required |
| Source identity verified / backup type / completion / recovery point / expiry (UTC) | Not verified — required; restricted evidence reference only |
| Schedule / last success / missed-job alert test | Not verified — required |
| Independent copy / encryption / key recovery | Not verified — required |
| PITR recovery range / archive continuity | Not verified; required if chosen for RPO |
| Target identity / isolation / compatible release / roles | Not verified — required for real-backup drill |
| Checksum / archive inventory / restore outcome | Synthetic archive verified only; actual backup not verified |
| Integrity / sequences / auth / media / external reconciliation | Synthetic row/catalog checks passed historically; actual production recovery not verified |
| End-to-end measured RPO/RTO / acceptance / cleanup | Actual-backup drill not performed; owner sign-off missing |

Changes in this task are documentation only: this audit/checklist and the corrected Phase 2 restore target guidance. No runtime/checker changes, production access or deployment.

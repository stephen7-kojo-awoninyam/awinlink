# Railway PostgreSQL backup and restore plan (Phase 2)

This is an operational plan only. No production database, backup, Railway service,
credential, or production setting was accessed or changed for Phase 2. Run the
steps below only under an approved maintenance/change window with an operator
who has the required Railway access.

## Current readiness

Updated offline assessment and recovery checklist: [backup/restore readiness audit, 2026-10-28](backup-restore-readiness-audit-2026-10-28.md). The snapshot/PITR target distinction below corrects the older drill wording; it is not permission to access production.

The last metadata-only readiness check, recorded in `security-phase1.md` on
2026-10-20, found no Railway volume backups or backup schedule, PITR disabled,
and no verified restore drill. This phase did not repeat that check or connect to
production. Until an operator verifies fresh backups and a successful isolated
restore, recovery readiness is unproven.

## Establish backups

1. Confirm the production service, environment, attached volume, retention needs,
   data owner, recovery point objective (RPO), and recovery time objective (RTO)
   through the approved Railway account. Do not paste project IDs, connection
   strings, backup URLs, or credentials into this repository or logs.
2. In Railway's service/volume backup controls, configure an automated snapshot
   schedule and retention policy appropriate to the agreed RPO. Confirm a new
   backup completed and is retained. A snapshot protects the Railway volume;
   separately inventory any external/offsite logical backup arrangement.
3. If point-in-time recovery is required, schedule PITR enablement separately.
   Railway documents that enabling it provisions/changes a database service and
   requires an operational change. Do not enable it as part of this plan.
4. Record only non-sensitive evidence: completion timestamp, retention, backup
   type, owner, and outcome. Keep the restore credentials in the approved secret
   manager.

## Restore drill in isolation

1. Choose the recovery method before selecting a target. Railway's documented
   **volume snapshot restore applies to the existing service**; it is not an
   isolated sibling-service drill. Do not stage or apply a production snapshot
   restore for a rehearsal. Its documented PITR workflow creates a sibling beside
   the source, not automatically an isolated environment. For a drill, prefer an
   approved existing logical archive restored into a separately provisioned,
   isolated non-production target. Any PITR sibling needs separately approved
   provisioning and verified network/application isolation before use. Verify
   the current provider workflow and target identity with an authorized operator.
2. For a logical backup workflow, an authorized operator may create a custom-format
   `pg_dump` using a least-privilege credential and restore it with `pg_restore`
   into that isolated target. This step reads source data and is outside this
   plan's execution; do not run it without explicit approval. Encrypt the artifact
   at rest and in transit, restrict access, set deletion/retention dates, and
   exclude credentials and dumps from shell history, CI logs, and Git.
3. Keep the restored database unreachable from production applications. Use a
   temporary isolated app/test environment and inject the new service URL through
   the approved secret manager. Do not overwrite production variables, point a
   production service at the restored database, or copy restored data back.
4. Validate database connectivity, schema/migration consistency, row counts and
   representative application reads using approved checks. Avoid dumping personal
   data in output. Record duration, recovered timestamp, validation result, and
   cleanup owner. Delete the isolated database and temporary artifacts after the
   drill under the approved retention policy.
5. A production recovery or cutover requires a separate incident/change decision,
   explicit approval, verified backup, and a rollback plan. This drill has no
   production cutover step.

## References

- [Railway: Back Up and Restore Postgres](https://docs.railway.com/guides/postgres-backups-restores)
- [Railway: Point-in-Time Recovery](https://docs.railway.com/volumes/point-in-time-recovery)

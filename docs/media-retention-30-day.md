# Media retention and erasure queue

Portfolio and event media now use a durable 30-day retention queue. Deleting a
portfolio item, event gallery item, or event captures its file/image references in
the same database transaction that removes the application records. Replacing a
portfolio file or event image queues the detached original as well. A transaction
rollback therefore cannot leave an erasure request for a still-referenced record.

The deadline is 30 days after the most recent queued removal for the same stored
name. The queue checks all installed Django `FileField` and `ImageField` references;
one remaining reference blocks erasure. A later removal adds its own retention
window, so it extends the effective deadline. Active legal holds take precedence.
Superusers can create and release audited holds in Django admin; hold identity and
reason are immutable, released holds cannot be reactivated, and holds cannot be
deleted from the admin.

Queue states include pending, held, shared, unresolved provider identity, ready,
erased, and failed. `process_media_erasure_jobs` only advances eligibility state.
`erase_ready_media_jobs` defaults to a dry run. Its explicit `--apply` path
rechecks holds, retention, live references, backend, and provider identity while
locking the relevant queue rows. Local paths must resolve inside `MEDIA_ROOT`.
Cloudinary deletion requires the captured cloud account, immutable provider asset
ID, resource type, and delivery type, then sends an invalidation request. Failures
remain retryable and do not become successful erasure. Repeated requests are
idempotent. No erasure command was run for this change.

Legacy Cloudinary files are never assumed to use the current namespace's delivery
type. They remain unresolved until an active superuser runs the read-only
`verify_media_erasure_identity` command with provider metadata. That verification
checks the exact public ID and asset ID; it does not delete. Historical provider
objects with no remaining database reference are outside this request queue and
still require a separately reviewed inventory and provenance/retention decision.
Backups, provider derivatives beyond the provider invalidation request, and assets
owned by other subsystems retain their existing separate policies.

Tests cover endpoint authorization, access revocation, file replacement, exact
30-day deadlines, later shared-reference removals, active/released holds, duplicate
enqueue, unresolved legacy delivery types, read-only dry runs, apply-time
rechecks, typed Cloudinary calls with mocked provider APIs, and concurrent
PostgreSQL queue workers. Tests use isolated media/database fixtures; no live
provider deletion or deployment was performed.

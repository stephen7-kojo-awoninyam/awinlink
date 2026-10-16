# Learning classroom services

Use `learning.classroom_services` for classroom business operations. Pass the
authenticated user as `actor`; obtain that user from server authentication, never
from a request body's user identifier. Functions accept saved objects or IDs for
classrooms, lessons, sessions and participants. They return the resulting model
and raise Django `PermissionDenied` or `ValidationError` on refusal. No signaling,
transport, API endpoints, push delivery or deployment behavior is added here.

| Operation | Course creator | Active assigned HOST | Admitted assigned COHOST | Learner |
| --- | --- | --- | --- | --- |
| Create classroom; assign staff | Yes | No | No | No |
| Schedule session | Yes | Own classroom | No | No |
| Start, end, cancel | Yes | Own admitted session | No | No |
| Admit/remove learners | Yes | Own admitted session | Own admitted session | No |
| Admit/remove cohosts | Yes | Yes | No | No |
| Remove host | Yes | No | No | No |
| Request admission | Requires enrollment | Staff already admitted | Staff already admitted | Requires enrollment |
| Join | Requires active assigned membership and admission | Same | Same | Also requires enrollment |
| Leave | Own connection only | Own connection only | Own connection only | Own connection only |

There is no administrator or account-role bypass for another creator's classroom.
Authorization re-reads account activity, assignments, admission and enrollment.
Only the course creator can assign staff. Staff transfers update scheduled
sessions atomically and are refused while any session in that classroom is live.

`create_classroom` assigns a host (the creator by default). If another host is
provided, the creator receives a cohost membership. `schedule_session` requires
timezone-aware future start/end times and admits active assigned staff. A host may
start early. `request_admission` creates a waiting participant for an enrolled
learner; `admit_participant` is required before `join_session`. Learners cannot
restore denied or removed admission themselves. `remove_participant` closes
attendance before revoking admission. `end_session` closes all attendance with
the session end timestamp. Cancel only scheduled sessions; end live sessions.

Capacity includes all admitted participants, including staff, and admission
reserves a seat even before the participant connects. A leave frees the connection
but preserves admission and its reserved seat; removal releases the seat. Capacity
cannot be reduced below an active or scheduled session's reservations.

For `join_session` and `leave_session`, supply `connection_id` as a UUID. Use a
fresh UUID for each new connection, and reuse it for retries of that same join.
A reconnect atomically closes the old interval and opens the new one. Leaving
with an older UUID affects only its interval. Replaying a closed UUID fails.
Repeated join, leave, admission, start, end and cancel calls do not duplicate their
audit events. Admission and identity checks run before idempotent returns.

Services and model writes lock the classroom first. PostgreSQL row locks serialize
capacity checks, admission, removal and reconnects. SQLite does not provide row
locking; callers must handle/retry database lock errors. Concurrency tests run only
on databases supporting `SELECT FOR UPDATE`.

Each state change and audit event commits in one transaction. Audits cover classroom
creation, staff changes, scheduling, admission requests, admission, joins, leaves,
removal, ending and cancellation. An audit insertion failure rolls back the change.

Classroom model `save`, `QuerySet.update`, `bulk_update` and `bulk_create` validate
persisted relationships and constraints. Bulk batches roll back on any invalid row.
Expression updates and conflict-skipping bulk inserts are refused. Relationships,
connection identities, session start/end timestamps and closed attendance are
protected against rewrites. These trusted ORM methods enforce integrity; callers
must still use services for actor authorization and audit logs. Raw SQL and Django's
internal write methods only receive the database's scalar and uniqueness checks.

Migration `0009_classroom_service_integrity` backfills a distinct connection UUID
for every existing attendance interval before making the column non-null and unique.

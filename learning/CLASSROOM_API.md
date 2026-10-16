# Learning classroom REST API

Base URL: `/api/learning/`. All endpoints use existing DRF JWT/session
authentication and require an active account. Use `Authorization: Bearer <token>`
for JWT requests. Session-authenticated mutations also require a valid CSRF token.
Send mutation payloads as JSON; use `{}` for actions without input fields.

| Method | Relative path | Input / behavior |
| --- | --- | --- |
| GET | `classrooms/` | Paginated authorized classrooms; optional `course` filter |
| POST | `classrooms/` | `course`, `title`, optional `capacity` (default 50) and `host`; course creator only |
| GET | `classrooms/{classroom_id}/` | Authorized classroom details |
| GET | `classrooms/{classroom_id}/sessions/` | Paginated session metadata, including only the caller's participant record |
| POST | `classrooms/{classroom_id}/sessions/` | `lesson`, `title`, `scheduled_start`, `scheduled_end`; creator or assigned HOST |
| GET | `sessions/{session_id}/` | Session metadata and caller's participant record |
| GET | `sessions/{session_id}/participants/` | Paginated staff-only roster and admission queue |
| POST | `sessions/{session_id}/request-admission/` | Enrolled caller requests their own admission |
| POST | `sessions/{session_id}/start/` | Creator or admitted assigned HOST |
| POST | `sessions/{session_id}/join/` | `connection_id` UUID; admitted eligible caller only |
| POST | `sessions/{session_id}/leave/` | `connection_id` UUID; caller's own connection only |
| POST | `sessions/{session_id}/participants/{participant_id}/admit/` | Creator, admitted HOST or COHOST, subject to service role hierarchy |
| POST | `sessions/{session_id}/participants/{participant_id}/remove/` | Same hierarchy; closes attendance before revoking admission |
| POST | `sessions/{session_id}/end/` | Creator or admitted assigned HOST; closes all attendance |
| POST | `sessions/{session_id}/cancel/` | Creator or admitted assigned HOST; scheduled sessions only |
| GET | `sessions/{session_id}/attendance/` | Staff see all intervals; learners see only their own |
| GET/POST | `classrooms/{classroom_id}/invitations/` | Creator/HOST list or invite; POST `recipient`, optional `message` and `expires_at` |
| GET | `classroom-invitations/` | Caller's own paginated invitation inbox |
| GET | `classroom-invitations/{invitation_id}/` | Recipient-only invitation details |
| POST | `classroom-invitations/{invitation_id}/accept/` | Recipient accepts; enrolls in approved course and adds a LEARNER membership |
| POST | `classroom-invitations/{invitation_id}/decline/` | Recipient declines without enrollment |
| POST | `classrooms/{classroom_id}/invitations/{invitation_id}/revoke/` | Creator/HOST revokes a pending invitation |

Creation and scheduling return `201`. Other successful reads/actions return `200`.
Lists return `{ "count": ..., "next": ..., "previous": ..., "results": [...] }`.
Pagination defaults to 20 results; `page` and `page_size` are supported, with a
maximum page size of 100. All responses include `Cache-Control: private, no-store`.

Course creators and active assigned staff can discover their classrooms. Enrolled
learners can discover active classrooms on approved courses; an inactive classroom
membership overrides enrollment access. Other object IDs return `404`. An ADMIN
account has no automatic classroom-management or attendance-access bypass.
Read access does not grant permission to join: services recheck assignment,
enrollment, admission, capacity and lifecycle state for every operation.

Unknown input fields are rejected. Caller identity comes from authentication;
clients cannot submit `actor`, `user`, `created_by`, `role`, admission state,
session status, timestamps of actual attendance, or audit metadata. A creation
request's optional `host` assignment is accepted only from the course creator.
Scheduling requires ISO-8601 timestamps with an explicit offset and a future
start before the end. The lesson must belong to the classroom's course.

Learner flow: request admission, obtain the returned participant ID, wait for
HOST/COHOST admission, then join with a fresh UUID. Staff obtain waiting participant
IDs from the roster. Join/leave responses include the caller's connection UUID;
attendance and roster reads do not expose connection UUIDs or account contact data.

Reuse a connection UUID only for retries of the same join. A new connection uses
a new UUID and atomically closes the previous interval. A delayed leave using the
older UUID cannot disconnect the newer connection. Closed UUIDs cannot be replayed.
Leave cleanup remains available for the caller's own participation after removal,
unenrollment, or classroom deactivation. All mutation behavior, capacity checks,
transactions and audit logs come from `learning.classroom_services`.

Errors use one envelope:

```json
{
  "error": {
    "code": "invalid_request",
    "detail": "Invalid request.",
    "fields": {"connection_id": ["Must be a valid UUID."]}
  }
}
```

`fields` appears for input/model validation. Statuses include `400` invalid input,
capacity or lifecycle; `401` authentication; `403` permission; `404` missing or
inaccessible objects; `405` unsupported method; `409` database conflict; and `415`
unsupported content type. Unexpected failures return a generic `500` error while
diagnostics stay in server logs. SQL, internal exception messages and private
account details are not returned. Existing learning routes and their response
formats are unchanged.

Invitations are classroom scoped and can only grant LEARNER membership. Creation
returns `201`; a repeated pending invitation returns the existing invitation with
`200` and sends no duplicate notification. Default expiry is seven days; an
explicit timezone-aware expiry must be within 30 days. Only one pending invitation
per classroom/recipient is allowed by the database. Expired invitations cannot be
accepted; creating another marks the old one expired. Declined/revoked invitations
are final. Active members and staff cannot be reinvited, and invitations cannot
restore inactive memberships. Acceptance rechecks the inviter's current authority,
recipient activity, classroom activity and course approval. It does not admit the
recipient to any session or reserve a capacity slot. Enrollment requires recipient
consent and follows the existing approved-course enrollment rule.

Classroom alerts appear through the existing `/api/notifications/` API with
read-only `metadata` containing `classroom_id`, optional `session_id` or
`invitation_id`, and `event`. Invitation creation alerts the recipient; acceptance
or decline alerts the inviter. Scheduling, starting, cancellation and ending alert
eligible active classroom members, except the action's sender. Learners must remain
enrolled; denied/removed session participants are excluded from later lifecycle
alerts. Notifications never grant access. The existing post-commit signal publishes
web push, Expo native push and realtime updates. Dispatch suppresses alerts when
access has been revoked or the lifecycle event is stale. Push payloads contain only
allowlisted routing data and never invitation messages, contact details or connection
UUIDs. Existing incoming-call push behavior is unchanged.

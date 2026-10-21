# Learning-Mode VC whiteboard

This is a persisted, authoritative object board, independent of video signaling and existing calls. It uses the configured Channels layer (Redis in production); no new deployment or push configuration is needed.

## Access and transports

`GET /api/learning/sessions/{session_id}/whiteboard/` returns a reconnect snapshot. `POST` to the same URL submits a command. HTTP uses existing DRF authentication and the classroom error envelope; stale revisions return 409, invalid input 400, unauthorized access 403. Responses are private/no-store.

Connect to `/ws/learning/sessions/{session_id}/whiteboard/` with existing authenticated browser session cookies (including the existing CSRF protection for HTTP writes), or native/mobile Authorization Bearer headers. Query tokens and all query parameters are rejected. Browser Origin validation and existing JWT/session authentication middleware apply. JWT expiry and session logout are checked on every message and on the idle watchdog.

Only currently admitted, active members can read. Learners must remain enrolled in an approved course. HOST and COHOST can edit; only the admitted HOST can grant/revoke learner editing and clear the board. Creator/admin account status alone never bypasses admission. Editing requires a LIVE session. ENDED sessions retain admitted-member, read-only access; cancelled/inactive sessions are unavailable. Removal and membership/enrollment revocation close access. A learner's grant expires on removal and re-admission, even if the participant ID is reused.

## Snapshot and commands

The socket initially sends `{"type":"snapshot","session_id":123,"revision":0,"objects":{},"editors":[],"can_edit":true,"can_manage":true}`. Objects are keyed by UUID. `editors` contains currently granted learner participant IDs. A client can request a fresh snapshot with `{"type":"snapshot"}`; HTTP GET returns the same fields without `type`.

Every command has exactly these four fields:

```json
{
  "operation_id": "116e47d0-8b7e-4d09-b68e-f366e8f7ec59",
  "base_revision": 0,
  "action": "add",
  "payload": {
    "id": "2f0d706c-97cf-4e32-90ed-08b8de7fa641",
    "kind": "rectangle",
    "color": "#3366aa",
    "width": 0.01,
    "x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4
  }
}
```

| Action | Payload | Behavior |
| --- | --- | --- |
| `add` | One new object | Drawing, text or shape; existing IDs cannot be overwritten |
| `erase` | `{"ids":["object-uuid"]}` | Erases 1–100 existing objects; editing grants permit shared-object erasure |
| `undo` | `{}` | Reverses only your own immediately preceding add/erase/clear; subsequent changes block undo |
| `clear` | `{}` | Host clears all objects |
| `permission` | `{"participant_id":42,"allowed":true}` | Host changes a same-session admitted learner's grant |

Objects always contain canonical UUID `id`, `kind`, six-digit hex `color`, and normalized `width` (.0001–.1). Additional fields are strict:

| Kind | Additional fields |
| --- | --- |
| `stroke` | `points`: 2–2048 `[x,y]` pairs |
| `text` | `x`, `y`, plain `text` (1–2000 characters), `size` (.001–.2) |
| `rectangle`, `ellipse` | `x`, `y`, `w`, `h` |
| `line` | `x`, `y`, signed endpoint offsets `w`, `h` |

Coordinates and endpoints use a fixed normalized canvas [0,1], so browser and mobile dimensions do not affect synchronization. Rectangle/ellipse sizes are nonnegative. Render text with canvas text drawing or textContent, never HTML. No URLs, markup fields, SVG, executable content, nonfinite numbers or client-selected room/actor IDs are accepted. Erasing removes complete objects. To implement a drag, preview locally then submit the completed shape/stroke; keep any optimistic preview separate from the authoritative snapshot.

Successful writes return `{"operation_id":"...","revision":1,"replayed":false}` (socket `type: "ack"`). All members receive a replacement snapshot after each commit. Replace local authoritative state and discard snapshots older than the current revision. Serialize outgoing changes; after a conflict, refresh and rebuild the operation using a new UUID and the current revision. Lost acknowledgements can be retried with the exact original command and UUID; retries are actor-bound and idempotent, but still require current editing authority. Socket errors use `type: "error"` and `code: invalid_request|permission_denied|conflict`; conflicts also send a fresh snapshot.

Root classroom row locks serialize HTTP/socket commands and permission changes. Board changes and immutable operation audit records commit together. Snapshots and operation inverses persist in the database, surviving client/process reconnects. The idle watchdog rechecks revisions and access, recovering even when a Redis notification was lost. Redis failures do not roll back an already committed drawing. Whiteboard connections never create, replace or close video attendance/signaling leases.

Commands are limited to 64 KiB, socket burst 30 with 10 commands/second refill; HTTP writes use DRF's per-user 600/minute cache throttle. Binary frames are rejected. Boards contain at most 1000 objects and 2 MB of serialized object data. Socket close codes: 4400 invalid query/binary/oversized frame, 4401 authentication, 4403 access revoked, 4404 missing session, 4408 rate limit, 4503 transport/database unavailable (retryable). Reconnect with fresh credentials and load a snapshot. Apply migration `0012_session_whiteboards` through the normal release process.

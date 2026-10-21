# Learning classroom WebSocket signaling

Connect to `/ws/learning/sessions/{session_id}/?connection_id={UUID}`. Native
clients use the same `Authorization: Bearer <access-token>` header as the existing
call sockets. Browsers can use existing authenticated session cookies and must
send an allowed origin. Tokens in URLs are refused. An invalid supplied bearer
credential does not fall back to a browser session for classroom sockets.

Use the existing `/api/messaging/calls/ice-servers/` endpoint for STUN and
short-lived TURN credentials. SDP descriptions and candidate objects are standard
WebRTC objects, compatible with browser/native RTC utilities. No existing call
consumer, media utility, call API or call route is changed.

Only active users with an active matching classroom membership and an ADMITTED
session participant can connect. The session must be LIVE and the classroom
active. Learners must still be enrolled in an approved course. Course creators,
hosts and administrators have no signaling admission bypass. Waiting participants
use the REST request/admit flow first. Socket connection reuses the existing
transactional join service and its attendance/capacity checks.

The connection response contains server-controlled `session_id`, `participant_id`,
`user_id`, `role`, `generation`, the caller's `connection_id`, and an online `peers` list. Peers
contain only participant IDs, user IDs, classroom roles and generation tags. A `presence` event
contains the updated peer list. No contact details, connection UUIDs or channel
names of other peers are exposed.

Send offers/answers to the peer's **session participant ID**, not their user ID:

```json
{
  "type": "offer",
  "recipient_id": 123,
  "description": {"type": "offer", "sdp": "v=0\r\n..."}
}
```

An answer uses `type: "answer"` in both places. ICE uses:

```json
{
  "type": "ice_candidate",
  "recipient_id": 123,
  "candidate": {
    "candidate": "candidate:1 1 udp 2122260223 192.0.2.1 54321 typ host",
    "sdpMid": "0",
    "sdpMLineIndex": 0
  }
}
```

`candidate: null` or an object with an empty candidate string marks end of
candidates. `usernameFragment` is optional. Unknown fields, forged identities,
room selectors, malformed SDP/ICE, duplicate JSON keys and non-finite JSON values
are refused. Text frames are limited to 64 KiB, SDP to 32 KiB, and candidates to
4 KiB. SDP must have valid line structure and core SDP headers; the RTC engine
still performs negotiation and codec/DTLS validation. Binary frames are refused.
Each socket has a burst allowance of 60 messages and replenishes 20 per second.

The server adds `sender_id` (user ID), `sender_participant_id`, `sender_generation`, and `session_id`.
Signals go only to the named online, admitted peer in the same session. They are
never broadcast to the room. Both sender and recipient are rechecked on delivery;
queued signals from removed, expired or replaced connections are dropped. Sending
`{"type":"ping"}` returns `{"type":"pong"}` after authorization checks.

Use a fresh connection UUID for each reconnect. One signaling channel owns the
participant's open attendance interval. A new socket fences the previous owner,
and an old disconnect cannot close the new interval. Taking over an existing open
UUID is also fenced; a UUID whose attendance has closed cannot be replayed.
REST leave/reconnect, participant removal, ending and cancellation emit room
controls only after their transaction commits. A rollback emits no control event.

JWT expiry closes even an idle connection. Token refresh requires reconnecting
with a fresh access token; no token refresh message is accepted. Browser session
logout, account inactivity, enrollment changes and role/admission changes are
checked again during activity and by the watchdog. Default heartbeat is 5 seconds;
the presence lease is 30 seconds. Expired leases disappear from presence and cannot
relay signals. Worker loss cannot leave a permanently online peer; stale attendance
closes on reconnect, leave or session ending. Attendance disconnect cleanup is
channel-fenced, including when authentication has expired.

Clients must close/rebuild an RTC peer connection when its public generation tag
changes, even if a fast reconnect leaves the participant ID unchanged. Generation
tags are opaque versions, not channel addresses or authorization credentials.
Clients must close their RTC peer connections when peers leave, the socket closes,
or `removed`, `replaced` or `session_ended` arrives. This consumer transports
signaling only; media remains with the existing WebRTC implementation.

| Close code | Meaning |
| --- | --- |
| 4400 | Invalid connection UUID/query, binary or oversized frame |
| 4401 | Authentication expired, invalid or revoked |
| 4403 | Admission or classroom access denied/revoked |
| 4404 | Missing session |
| 4408 | Message rate exceeded |
| 4409 | Connection replaced, closed, or lease expired |
| 4410 | Session no longer live |
| 4503 | Channel-layer or database unavailable (retryable) |

The existing `REDIS_URL` configuration selects `channels_redis` for all workers;
no separate Redis client or authentication system is introduced. Room groups use
`learning.session.{id}` and peer groups use
`learning.session.{id}.participant.{participant_id}`, isolated from `call_{id}` and
`user_{id}`. Redis control failure does not undo committed removal/ending; watchdogs
and per-message authorization still enforce access. Refreshing group membership
and database leases supports long-lived browser sessions. Production concurrency
uses the existing PostgreSQL row locks; SQLite remains a local test backend.

Migration `0011_classroom_signaling_presence` adds nullable channel/heartbeat fields
to attendance intervals. REST serializers keep these internal fields private.
Security tests use the actual ASGI authentication/routing and Channels' in-memory
layer. To exercise Redis itself, set `CLASSROOM_TEST_REDIS_URL` to a dedicated test
Redis instance and run `learning.test_classroom_signaling`; the integration test
uses a unique key prefix and does not flush Redis. Without that explicit test URL,
the Redis integration test is skipped.

The application uses private close codes for invalid frames and temporary unavailability because the installed Daphne/Autobahn server rejects reserved application-supplied codes 1003, 1009 and 1013. Clients treat 4400 as terminal and retry 4503 with the existing bounded backoff.

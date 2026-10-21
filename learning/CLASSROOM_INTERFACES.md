# Learning-Mode VC browser and mobile interfaces

Browser entry: `/learning/classrooms/`, linked from Learning navigation. Session page: `/learning/sessions/{session_id}/classroom/`. Native entry: `/classrooms`, linked from the existing Learning screen; session route `/classroom/[id]`. Expo web opens the corresponding full Django browser classroom, with its normal session login; it never puts a mobile JWT in a URL.

Both interfaces provide session discovery, admission requests, explicit join/leave, an audio/video participant grid, camera/microphone controls, supported screen sharing, host admission/removal/start/end/cancel controls, chat and the persisted whiteboard. Cameras and microphones are optional; joining with both disabled still negotiates receivers, and either device can be enabled later. Hosts can allow/revoke learner drawing, clear and undo; learners use the server's editing grant. Admission queues and classroom/session directories are paginated.

## Server authority and media

The browser uses existing session cookies and CSRF tokens for HTTP mutations. Native sockets use the existing Authorization Bearer header; tokens stay in SecureStore. Native reconnect first reads session details through the existing refresh-capable API client, then opens sockets with the refreshed access token. Session serializers now provide read-only `capabilities`; buttons reflect those capabilities, and every operation still runs the original permission-checked classroom service. The user’s account role never grants client-side host powers.

The shared `mobile/src/classrooms/client.js` controls WebRTC negotiations, queues ICE until remote SDP is available, deterministically selects one initial offerer and fences messages/connections by server peer generations. It calls the existing ICE-server API and uses browser RTC engines or the installed `react-native-webrtc` engines. It never opens existing `ws/calls/` rooms, mutates global call state, ends another call or changes an existing call utility.

Signaling sends are paced below the server limit, with a bounded queue; queued messages for a replaced peer generation are discarded. Disconnection closes owned peer connections and capture, and reconnect uses a fresh attendance UUID. Retry attempts are bounded with backoff. Removal, session ending and another connection taking over stop media; a replaced tab/device never automatically takes over again. Late media acquisition after leaving is stopped. Leaving and navigation dispose media, both sockets and timers, and call the existing leave endpoint. Whiteboard socket reconnects are independent of video leases.

Screen sharing replaces the video sender track and restores the camera when sharing stops; it preserves microphone audio. Browser sharing is offered only when `getDisplayMedia` exists and requires the normal secure browser context and explicit picker consent. Android uses the existing RTC module's MediaProjection service; the local Expo config plugin enables that service and declares the required foreground-service permissions. These config changes require the normal native development/release build to take effect; no build or deployment was performed here. iOS sharing is hidden because this app has no ReplayKit broadcast extension. Camera/microphone media closes when a native app backgrounds, except during explicitly started screen sharing. Stopping sharing in the background closes remaining classroom media.

Native whiteboard strokes use bounded display sampling to limit the number of native drawing views; full geometry is always sent and persisted. Erasing removes an entire object. Text uses canvas text/DOM textContent/native Text; chat never renders user HTML. Live whiteboard writes use the same revision and undo rules documented in `WHITEBOARD_API.md`; no edits are queued across reconnects or permission changes. Screen/media permission denial leaves clear error states and permits joining again with devices disabled.

## API map

| Interface flow | HTTP endpoint under `/api/` | Server adapter |
| --- | --- | --- |
| Classroom/session discovery | GET `learning/classrooms/`, `learning/classrooms/{id}/sessions/` | Existing classroom list/schedule views and read-only serializers |
| Session status/capabilities | GET `learning/sessions/{id}/` | SessionDetailAPIView / LiveSessionSerializer |
| Admission request | POST `learning/sessions/{id}/request-admission/` | SessionRequestAdmissionAPIView / original service |
| Join/leave | POST `learning/sessions/{id}/join/`, `leave/` with connection UUID | Existing join/leave views / attendance services |
| Host actions | POST session `start/`, `end/`, `cancel/`, participant `{pid}/admit/` or `remove/` | Existing classroom permission/service views |
| Roster | GET session `participants/` with pagination | SessionParticipantsAPIView / SessionParticipantSerializer |
| STUN/TURN | GET `messaging/calls/ice-servers/` | Existing CallIceServersAPIView |
| Whiteboard | GET/POST session `whiteboard/` | Existing WhiteboardAPIView / transactional whiteboard service |
| Chat | GET/POST session `chat/` | New ClassroomChatAPIView / admission-protected chat service |

Video signaling uses the existing `/ws/learning/sessions/{id}/?connection_id={UUID}` protocol. Whiteboard/chat share `/ws/learning/sessions/{id}/whiteboard/`. Existing whiteboard messages are preserved. Chat adds:

```json
{"type":"chat","client_id":"63b6e1de-6c6d-4dc9-a668-8306c314ba6a","text":"Hello classroom"}
```

Delivery: `{"type":"chat","message":{...}}`, with server-controlled `id`, `client_id`, `sender_id`, `sender_name`, `text`, `created_at`. `{"type":"chat_history","after":123}` returns `{"type":"chat_history","messages":[...]}`. History defaults to the latest 100 messages; `after` retrieves up to 100 newer messages. HTTP uses `?after=123`, returning `{"results":[...]}`. Clients deduplicate by server message ID; retries use the original client UUID and text. Sending requires a LIVE session and current admission/enrollment; ended history is read only. Removed members cannot read or receive queued messages. Chat and whiteboard grants are separate: viewing-only learners may still chat.

## Change inventory

Backend additions: `classroom_views.py` and the two browser templates provide authorized page shells; `classroom_chat.py`, `ClassroomChatMessage` and migration `0013_classroom_chat` add immutable, deduplicated session chat. `whiteboard_api.py`, `classroom_api_urls.py`, and `whiteboard_consumer.py` expose/deliver chat with the existing authentication, origin, rate, CSRF and admission checks. `classroom_serializers.py` adds server capabilities and safe participant names; `classroom_api_views.py` preloads participant users. `learning/urls.py` and the Learning nav add browser routes. No changes to existing call, messaging or push implementations were needed for this task.

Browser files: `static/js/classroom-browser.js` adapts/render controls, media, chat and canvas; `static/css/classroom.css` provides the responsive grid/panels. `static/js/classroom-client.js` is generated from the shared native controller.

Mobile files: `app/classrooms.tsx`, `app/classroom/[id].tsx` and its `.web.tsx` adapter provide navigation and screens; `src/classrooms/client.js`/`.d.ts` and `Whiteboard.tsx` provide the controller and native drawing; `app/learning.tsx` links the directory. `src/api/client.ts` only adds parsing of the existing classroom error envelope. `plugins/withClassroomScreenShare.cjs`/`app.json` configure Android sharing. `scripts/build-classroom-client.cjs`, `package.json` and `tests/classroom-*.test.cjs` provide the bundle and focused test commands. `learning/test_classroom_interfaces.py` adds server/API/socket security tests.

## Verification and operational limits

From `mobile/`: `npm run build:classroom-client`, `npm run test:classroom`, `npm run typecheck`. Set `CLASSROOM_TEST_CHROME` to an installed Chrome binary to run the headless browser smoke test; otherwise that test is skipped. It uses synthetic media/API/socket fixtures and an isolated temporary workspace profile. The shared-client tests cover negotiation, reconnect fencing, media cleanup, screen replacement, rate pacing, board grants and revision ordering. Django tests cover session scopes, server capabilities, chat admission/enrollment/removal, CSRF, identity spoofing, persistence and socket isolation.

Apply generated migration `0013_classroom_chat` through the normal release process. The production Channels layer continues to use the existing Redis configuration; the test suite uses in-memory Channels and SQLite, so PostgreSQL concurrency/dedicated Redis tests require their separate test environments. Real microphone/camera capture, TURN traversal, Android projection prompts, iOS playback and multi-device calling have not been verified on physical devices or emulators. Media is the existing peer-to-peer mesh, not a newly introduced SFU.

No commit, push or deployment was performed. Unrelated working-tree changes were preserved.

## Phase 1 management interfaces

The web and native Live classrooms directories now include classroom creation, session scheduling, invitation responses, sent invitation review/revocation, and cohost management. Web entry remains `/learning/classrooms/`; native entry remains `/classrooms` from Learning. Expo web uses the same management components and continues to open media classrooms in Django.

Creators select an owned course and set classroom title/capacity. The creator is the initial host. Creators and assigned hosts select a course lesson and provide a session title and future start/end. Browser datetime inputs use local time; native inputs accept `YYYY-MM-DDTHH:mm` in local time or an explicit offset. Both send timezone-aware ISO timestamps to the existing scheduling endpoint.

Invitations use the existing invitation APIs. A recipient can review and accept/decline from the directory; acceptance explains course enrollment and separate session admission. Managers can send and revoke pending invitations and paginate sent history. Recipient/cohost entry uses a scoped username search and explicit account selection; API writes retain internal numeric IDs. Sent invitations and staff show usernames. Invitation expiry uses the existing seven-day default.

Staff management uses GET/POST `/api/learning/classrooms/{id}/staff/`. GET returns a paginated active host/cohost roster. POST accepts exactly `{ "user": <positive ID>, "role": "COHOST" | "HOST" | "REMOVE" }`. It is restricted to the active authorized course creator; account ADMIN status alone does not bypass ownership. Assignments reuse `assign_classroom_role`. Removing a cohost deactivates their membership and removes scheduled-session admissions; reassigning them restores scheduled staff admissions subject to capacity. Staff changes are blocked while any classroom session is live. A host must be transferred rather than directly demoted or removed. UI confirmations explain that transferring host makes the former host a cohost.

Classroom responses now include read-only `capabilities.manage` and `capabilities.staff`. These guide UI visibility; service permissions remain authoritative. No migration is required.

The shared media controller now validates the ICE endpoint's `ice_transport_policy`, passes it to every browser/native peer, and defaults to `all` only when omitted by an older endpoint. A returned `relay` policy becomes `iceTransportPolicy: 'relay'`. Invalid policies fail before media capture.

Local verification: use `python -u -B scripts/vc_audit.py test learning.test_phase_one learning.test_classroom_api learning.test_classroom_invitations learning.test_classroom_security learning.test_classroom_interfaces --noinput`, plus mobile `npm run typecheck` and `npm run test:classroom`. Set `CLASSROOM_TEST_CHROME` to a Chrome executable for browser fixtures. These browser tests use synthetic APIs/media; they do not prove physical-device media, production TURN traversal, external push delivery, or PostgreSQL concurrency. No deployment was performed.


### Username search

GET `/api/learning/classrooms/{id}/users/?purpose=invite&q={username}` provides paginated, case-insensitive username substring search. `purpose=cohost` is restricted to the course creator; invitation search allows the creator or assigned host. Learners, noncreator cohosts, unauthenticated/inactive accounts and unrelated admins cannot use this as a user directory. The endpoint requires 2?150 characters, returns only `id`, `username`, `display_name`, uses a 30/minute per-user throttle, and sends private/no-store cache headers. It excludes inactive users and ineligible existing memberships, while allowing creator-authorized cohost restoration. Writes still recheck service permissions and target status after selection.

Both web and mobile clear the selected account and discard older search responses when query text changes. Results require explicit selection, and pagination preserves the search scope. Search, invitation and cohost paths remain under Learning ? Live classrooms. No schema migration or deployment is required.

Username-search validation: PostgreSQL 17.11 ran all 101 focused search, Phase 1, API, invitation, security and interface tests successfully with no skips. The nine search tests also passed on SQLite. Mobile TypeScript and the headless Chrome management-control test passed, including stale-selection prevention. PostgreSQL used the verified workspace audit cluster on 127.0.0.1:55432 and a disposable test database. Native device UI was not exercised.

The 2026-10-20 real teacher/learner browser audit passed 23 functional checks, including real synthetic-media RTP, invitation acceptance, drawing grants, chat, reconnect, removal and attendance cleanup. Four additional real Daphne socket checks verified invalid-frame closes. See `../docs/learning-vc-e2e-2026-10-20.md` for the exact backend rerun results, close-code correction and remaining verification limits.

# Learning Mode VC local end-to-end results

Run date: 2026-10-20. No deployment, commit or push was performed. Existing workspace changes were preserved.

## Browser results

The complete teacher/learner browser flow passed all 23 checks. It used synthetic COACH/ATHLETE accounts, a teacher-owned approved course and lesson, isolated authenticated Chrome contexts, real Django HTTP APIs and Channels sockets, two loopback ASGI workers, PostgreSQL 17.11, and Redis 8.10.2 (Windows port). API and socket responses were not mocked. Authentication used synthetic database sessions; the login form was outside this test.

| Flow | Result |
| --- | --- |
| Teacher creates classroom and schedules lesson through web forms | Passed |
| Teacher searches learner username and sends invitation | Passed |
| Learner accepts invitation, becomes enrolled and discovers classroom | Passed |
| Learner cannot search users, assign host, schedule or start sessions | Passed |
| Waiting learner cannot join through UI or direct API and does not capture media | Passed |
| Teacher starts session and admits learner | Passed |
| Teacher and learner join and exchange real audio/video RTP | Passed |
| Participant grid at 390px mobile browser viewport | Passed |
| Whiteboard teacher text, learner viewing, drawing grant, learner shape and undo | Passed |
| Learner cannot clear the board; other-session board reads are isolated | Passed |
| Chat in both directions; HTML-like message is rendered as plaintext | Passed |
| Camera/microphone toggles preserve the media session | Passed |
| Reconnect creates a new UUID, resumes RTP and restores chat/board | Passed |
| Attendance has exactly one open learner interval after reconnect | Passed |
| Drawing revocation updates the learner UI | Passed |
| A second admitted learner joins with both devices off, then leaves | Passed |
| Teacher clear synchronizes to learner | Passed |
| Removal stops capture and denies subsequent learner chat reads | Passed |
| Ending stops teacher capture and closes all attendance intervals | Passed |

RTP statistics showed inbound audio bytes and decoded video frames in both directions. The selected candidates were local/peer-reflexive, so this proves local browser WebRTC exchange with synthetic camera/microphone input, not TURN traversal or physical-device capture. This was a small classroom functional run, not a capacity/load test.

## Fixes

The installed Daphne/Autobahn transport rejects application-supplied reserved close codes 1003, 1009 and 1013. Local server logs exposed an exception when the whiteboard tried to close with 1013 during a temporary Redis failure. Signaling and whiteboard now use 4400 for invalid frames and 4503 for retryable database/channel-layer failures. Existing client backoff retries 4503; 4400 remains terminal. Four real network socket checks against Daphne passed for binary and oversized frames on both endpoints. A new unit regression calls the installed transport's actual close-code validator; existing Redis-error tests check the transient code, and client reconnect tests now exercise 4503.


The full Learning form stylesheet compressed the whiteboard color input until its swatch was barely visible. The classroom stylesheet now gives it a fixed usable width and smaller padding; the complete browser flow verified its width.

The audit harness now exercises creation, scheduling and invitations through the actual UI before media tests. It waits for page initialization and navigation, brings the canvas page to the foreground, performs an immediate scroll, and verifies pointer hit coordinates before drawing. Earlier drawing failures were caused by clicking while the page was still scrolling; those were harness failures rather than a whiteboard authorization or persistence defect. Failure diagnostics and screenshots are saved locally without session credentials.

## Other local checks

- Shared browser/native controller: all 25 tests passed.
- Mobile TypeScript: passed.
- Full Learning backend suite against isolated PostgreSQL and Redis: 203/205 passed on the first run; two whiteboard socket tests exceeded the original one-second waits. Both passed in the affected-suite rerun after increasing integration waits to five seconds.
- Post-fix signaling/whiteboard/interface suite: 55/57 passed in one run, including both original whiteboard failures. The two remaining checks (the new transport-validator test's setup and a three-second reconnect response wait) were corrected and passed a final focused PostgreSQL/Redis rerun. All 57 affected checks are therefore validated across the rerun and focused retries; a single final green run of the entire 205-test suite was not performed.
- The transport-validator test bypasses protocol construction so it can exercise Autobahn's actual close-code validation without selecting or starting a second txaio framework. Signaling integration helpers use five-second setup/close waits and a ten-second response wait. Production timers were not changed.
- Real Daphne network close checks: all four passed.
- Git whitespace check: passed (existing line-ending normalization notice only).

## Reproduction and evidence

Start the existing workspace-only services with `.venv/Scripts/python.exe -u -B scripts/vc_audit_resources.py start`. Prepare new synthetic fixtures with `scripts/vc_audit_server.py --prepare`, then run two instances with `--port 18765` and `--port 18766`. Set `CLASSROOM_TEST_CHROME` to the installed Chrome executable and run `node scripts/vc_browser_e2e.cjs`. Always prepare fresh fixtures for a full rerun; the test changes admissions and ends its session.

Run `node scripts/vc_wire_e2e.cjs` with the first local worker running to exercise real Daphne rejection/close frames; it uses the existing synthetic fixture and the installed mobile `ws` dependency. Results are saved to `.audit-vc-e2e/wire-close-e2e.json`.

The final successful browser evidence is `.audit-vc-e2e/browser-e2e.json` (23 passed checks, `success: true`). Fixture session cookies, local database files and browser profiles remain in ignored audit directories and are not release artifacts. Native Android/iOS builds, physical camera/microphone devices and permission prompts, forced TURN relay, real screen capture and external push receipt were not exercised. The local Windows Redis port emitted transient read timeouts during diagnostic runs; this audit does not establish production outage/failover behavior. No deployment was performed.

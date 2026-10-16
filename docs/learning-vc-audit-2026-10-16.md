# Learning-Mode VC audit

Audit run: 2026-10-16, against the current uncommitted workspace. No commit, push, or deployment was performed.

## Results

| Area | Result | Evidence and limits |
| --- | --- | --- |
| Migrations 0008-0013 | Passed on PostgreSQL 17.11 | Upgrade from 0008 with 53 already-admitted participants preserved classroom capacity and populated signaling UUIDs; tested schema constraints; empty feature schema rollback to 0007 and forward migration passed. A populated rollback against a sanitized staging copy was not run. `makemigrations --check --dry-run` reported no drift. |
| PostgreSQL concurrency | Passed on local PostgreSQL | The final focused run passed 10 migration, board revision, duplicate chat retry, session-end/write race, removal/chat race, and Redis integration tests with no skips. An earlier focused run passed 15 tests with no skips. This is a single local server, not a production load or failover test. |
| Redis signaling | Passed on local Redis 8.10.2 | Redis Channels integration and two Daphne workers on separate ports used the same Redis layer. The local Redis distribution is a Windows port; production Linux/TLS/ACL and outage behavior were not exercised. |
| Classroom permissions and services | Passed | Existing security and concurrency tests cover non-creators, non-hosts, waiting and unenrolled learners, admission, removal, capacity, and service validation. |
| REST API and existing calls | Passed in the previous full suite | Previous SQLite run: 229 tests passed, 6 PostgreSQL-only tests skipped; existing messaging/call test modules were included. PostgreSQL focused run: 15 tests passed with no skips. |
| Browser and mobile client logic | Passed | Shared client unit tests: 23 passed, including reconnect fencing, cleanup, safe admission, and chat pagination. `npx tsc --noEmit` passed. `git diff --check` passed with a line-ending warning for `learning/api_urls.py`. |
| Browser RTC, whiteboard, chat, reconnect, and attendance | Not verified end to end | Synthetic Chrome launched but stopped answering CDP at `Target.createBrowserContext`, including after increasing the command timeout to 60 seconds. A separate Django page probe returned the classroom page (200) in 25.76 seconds; both warm workers then returned 200. This does not establish a classroom or RTC defect. The audit harness records zero passed browser E2E checks. |
| TURN relay | Not verified | No TURN URLs/shared secret were configured, so forced relay candidate negotiation was unavailable. Credential-generation unit checks passed in the previous suite. |
| Push delivery | Not verified externally | No provider credentials/device registrations were configured. Existing notification tests validate recipient selection, payloads, and failure handling with provider calls mocked; no APNs/FCM/Web Push receipt was observed. |
| Native Android/iOS | Not verified | No attached device/emulator or signed development build was available. JavaScript client and TypeScript checks do not prove native media or screen-sharing behavior. |

## Confirmed fixes during audit

- Mobile call setup now compensates a successful attendance join if signaling setup fails, and an old connection cannot close a newer reconnect.
- Leaving while a screen track is being replaced no longer restores a released preview or stale sharing state.
- Mobile chat catch-up follows server pagination instead of silently skipping older messages.
- Whiteboard coordinate validation rejects oversized integers cleanly instead of raising an overflow error.
- Chat and whiteboard text reject invalid Unicode/control input before persistence.
- Whiteboard socket history and its periodic recovery cursor restore chat messages whose Redis notification was missed.
- Migration 0009 raises classroom capacity to fit existing admitted occupancy before applying the new capacity checks.

## Deployment blockers and follow-up

The audit did not deploy. Before release, run the migration upgrade on a sanitized PostgreSQL copy with realistic data and verify rollback policy, then exercise a browser and native build against the intended Redis, TURN, and push-provider environments. The audit fixtures, local service binaries/data, logs, and browser profiles are under ignored `.audit-vc-*` directories; they contain synthetic test accounts and must not be treated as release artifacts.

# API and realtime resource protection

Implemented locally; no deployment, production database/cache operation or
provider-file change was performed. Existing courses, memberships, messages,
uploads, consent records and history remain intact.

## Collection contract

High-cardinality custom lists in the main API, feed, learning, competitions,
events, portfolios, messaging and organization team management now paginate
before serialization. DRF generic list views use the same bounded default.
Existing endpoints with their own bounded pagination retain that contract.

The default is 50 items; `page_size` must be positive and is capped at 100.
Array bodies remain arrays. Follow the `Link` header's `rel="next"` URL to
continue. `page_format=cursor` explicitly requests
`{results, next, previous}` instead. There is no unbounded legacy switch or
automatic client loop that fetches every page.

Cursors are signed, expire after 24 hours, and bind to the user, endpoint and
filters. Authorization and visibility are evaluated again on every request.
Most lists seek on indexed primary keys. Curricula and ranked recommendations
use compound keys ending in the primary key, including when over 1,000 rows
share an order/score value. These pages do not use growing SQL offsets.
Configuration-managed learning categories retain their small taxonomy response;
computed recommendation responses already have explicit top-result limits.

The Expo native and web client retains continuation metadata outside JSON array
enumeration and presents explicit load-more controls. Local edits retain that
metadata, refreshes replace it, and late page responses cannot append after an
account switch, list replacement or unmount. Quizzes cannot submit while more
question pages remain. Lesson ordering and earlier quiz answers are preserved.
Message history starts with the newest page and displays messages chronologically.
The web unread badge uses an aggregate endpoint, rather than summing one page.
Search filters run on the server before pagination, with a bounded/debounced
query from the client. Saved/followed talent rows render independently of the
loaded directory page. Own relationship markers and parent-scoped registration
lookups preserve application/follow state and older submissions even when their
separate history page has not been loaded. Scout verification/name order, team
member order, competition standings (including unranked entries) and recent
conversation order are preserved with compound cursors where needed.

Conversation lists no longer prefetch complete histories: latest messages and
unread counts are fetched in batches for the selected page. Talent social counts
also run against page user IDs, avoiding a followers-by-following join product.
Organization follower counts no longer load every follower into Python. Event
visibility uses a participant-history subquery, avoiding registration fan-out
on published event rows before applying the page limit.

## Shared budgets

`AWINLINK_RESOURCE_LIMITS` in Django settings defines capacities and refill/lease
durations. Byte/frame/connect budgets are token buckets: the capacity is the
maximum burst and replenishes over the stated period, rather than resetting at
a fixed wall-clock boundary. Rejected attempts cannot reset a bucket.

| Resource | Default |
| --- | --- |
| Socket transports per account | 12 live leases, 45-second expiry |
| Socket transports across workers | 2,000 live leases, 45-second expiry |
| Authenticated reconnects per account | 60-token burst; refill in 60 seconds |
| Handshakes before authentication, per trusted client IP | 600-token burst; refill in 60 seconds |
| Frames across all transports for an account | 240-token burst; refill in 4 seconds |
| Concurrent multipart uploads per account/client IP | 4 leases, 120-second expiry |
| Concurrent multipart uploads across workers | 16 leases, 120-second expiry |
| Attempted authenticated upload bytes per account | 1 GiB burst; refill in one hour |
| Attempted anonymous upload bytes per client IP | 250 MiB burst; refill in one hour |
| Concurrent local FFmpeg jobs across workers | 2 leases, 90-second expiry |
| Concurrent producers of the same playback derivative | 1 lease, 90-second expiry |
| Non-multipart request body | 2.5 MiB |
| Multipart raw body | Existing 250 MiB file total plus 5 MiB metadata overhead |
| ASGI upload inactivity / total duration | 120 seconds / one hour |

Existing per-file, per-request, MIME/signature, CSRF, ownership and file-delivery
checks remain in force. Upload bytes include failed/abandoned work. Byte quotas
cover all file parts and endpoints for the authenticated account; submitted user
or organization IDs cannot select a different allowance. Browser sessions and
native JWT uploads share that allowance. JSON-only edits do not occupy upload
slots. These are ingress/work quotas, not a new lifetime storage entitlement or
an inventory/deletion policy for historical provider assets.

Uploads renew their leases during streaming and release them on request cleanup.
ASGI admits multipart requests against the shared global limit **before** Django
creates its body spool. It counts actual bytes even without a trustworthy content
length, aborts oversized/stalled requests through Django's disconnect cleanup,
and holds its admission lease through request completion. The multipart handler
borrows that lease, avoiding double counting and premature release. Completed
chunked requests receive their measured content length for Django's parsers.
WSGI rejects oversized JSON before DRF parsing, and retains its streaming file
checks. Existing files and internal generated-document writes are unaffected.
Socket leases are acquired before consumer/group work, renewed even when idle,
and released on teardown. Crash recovery relies on expiry; expired lease tokens
cannot renew or release replacement leases. Same-user JWT renewal retains the
existing lease and budgets. Cancellation drains in-flight acquisitions before
release, so a late backend response cannot strand a newly added lease. Completed
consumer/watchdog tasks are drained even when they finish together.
Pre-authentication IP handling reuses the existing
explicit trusted-proxy policy; unsolicited forwarded headers are ignored.

HTTP budget exhaustion returns 429 with `Retry-After`. Backend failure returns
503 without connection details; oversized bodies return 413 and upload timeouts
return 408. Socket limit/outage codes are 4008/1013, retaining 4408/4503 for the
existing classroom protocol. Existing
per-connection frame limits and credential/permission revocation remain active.
FFmpeg keeps its 60-second subprocess timeout, discards unbounded diagnostic
output rather than buffering it in worker memory, and leaves originals unchanged;
cached derivatives require no new processing slot.

Production resource protection requires Django's built-in Redis cache backend
through `AWINLINK_RESOURCE_CACHE_ALIAS`; `REDIS_URL` selects the existing security
cache automatically, including on Railway. Atomic Lua operations use Redis server
time and the writable primary, with separate HMAC key namespaces. A deploy check
(`awinlink.E003`) rejects process-local or unsupported resource backends. Local
memory protection is allowed only in explicit development mode. Health/startup
checks do not contact Redis or change its configuration.

## Validation and release dependencies

Security regressions use `scripts/test_security_phase1.py` with an isolated SQLite
database/media root. Real Redis races use independent worker processes through
`scripts/test_admin_security_redis.py config.test_resource_redis`: the runner starts
its own password-protected loopback Redis instance without persistence and shuts
down only that verified fixture. It never uses the application's Redis URL.

`scripts/rising_talent_audit.py api.test_pagination_security messaging.test_pagination`
checks the workspace PostgreSQL cluster's data directory before creating a unique
disposable database. It exercises the new index migrations and pagination queries.
Mobile pagination tests exercise one-page fetching, duplicate-tap fencing, stale
response rejection, URL validation, metadata preservation and complete quizzes.

Validation completed locally:

- 48 focused backend compatibility/security checks passed.
- 110 runtime/security checks passed (one Redis integration case skipped in that
  non-Redis runner), including native calls, revocation, classroom transports,
  cancellation cleanup, uploads and real FFmpeg conversion.
- 16 PostgreSQL checks passed, including online index migrations, tied/null/related
  ordering and preservation of existing organization roster consent/history.
- Four isolated Redis checks passed, including independent-worker quota races and
  the existing admin-login integration control.
- Mobile: 181 passed; three browser-dependent checks skipped. TypeScript passed.
- Migration drift and whitespace checks passed.

The broad 1,051-test run before the final ingress additions had one native-call
startup timeout under concurrent test load (all other checks passed; 34 skips).
That fixture now allows five seconds instead of one and always disconnects both
peers. The affected suites were re-run successfully in the 110-check runtime run;
production credential/lease deadlines were not relaxed. The final 87-check run
also passed, covering ASGI ingress, file/security quotas, production checks and
native socket regression tests, including a real chunked JWT upload under a
one-slot global limit.
The subsequent 35 collection/privacy regressions also passed after removing
event-registration join fan-out. Together, the final targeted runs passed 122
backend checks. ASGI body checks cover declared/actual limits, unknown lengths,
idle abort, spool cleanup, admission reuse and a real JWT multipart workflow.

Before any later release, review budgets against staging workload measurements
and available Redis/worker/disk capacity, and verify the existing trusted-proxy
configuration. Resource Redis must have suitable capacity and an eviction policy
that does not discard active protection keys. Loss/eviction of Redis state can
reset burst counters; renewal detects missing leases and closes affected sockets.
Do not interpret these functional/concurrency tests as a production capacity test.

The additive messaging, learning and analytics index migrations use concurrent
creation/removal on PostgreSQL and standard index operations on local SQLite.
They do not backfill or delete application records. Interrupted PostgreSQL online
index builds require inspection of index validity before a migration retry.
No production migration has been run.

Messaging realtime
==================

Web sessions and native Bearer JWTs connect to `/ws/user/` through
`config.asgi.application`. Run an ASGI server such as Daphne for HTTP and
WebSocket traffic, and allow WebSocket upgrade requests through the proxy.
Browser origins must match `ALLOWED_HOSTS`; native JWT sockets without an
Origin use the existing authenticated native route.

Set `REDIS_URL` to a shared Redis service for every ASGI/HTTP worker.
Without it, settings select InMemoryChannelLayer, which only delivers inside
one process and cannot support multiple workers. The current local environment
has no REDIS_URL. No Redis service or hosted configuration was changed.

Run `python manage.py check_realtime` to check group registration, send,
receive and cleanup on the configured channel layer. It sends an isolated
health event, never a user event. Run it in each environment using that
environment's settings.

Migration `0012_conversationparticipant_last_read_at` is required before
running the updated app. It preserves the available legacy read history;
the old shared is_read flag cannot recover historical reads per group member.
No migration was applied to the local application database in this change.

Messages publish only after commit, to current participants' user groups.
Delivery and typing recheck membership, active status and account blocks.
Clients reconcile history after reconnect; message IDs prevent duplicate
bubbles when the sender receives both HTTP and WebSocket results.
Typing expires locally, so disconnected clients cannot leave permanent indicators.

Native messaging reconnects with bounded exponential backoff, catches up on
foreground, and retains a 30-second history fallback. Django web uses the
existing global socket reconnect plus history reconciliation. Native sockets
use fresh tokens from the shared API client after HTTP reconciliation.

Validation: Django messaging tests use an isolated SQLite test database and
in-memory channel layer. `mobile/tests/messaging.test.cjs` exercises reconnect,
cleanup, typing and inbox events. A live Redis and device/browser end-to-end
session still require an environment with those services available.

# TURN credential and relay privacy hardening

Implemented locally on 2026-10-27. Nothing deployed; no environment variables, live credentials or relay infrastructure changed.

Credential issuance now uses the existing atomic resource limiter: each account has a token bucket with capacity 30 refilling over 60 seconds, plus capacity 300 refilling over one hour. These budgets live in `AWINLINK_RESOURCE_LIMITS` under `turn_credentials_burst` and `turn_credentials_hour`. Production uses the shared Redis security cache and fails closed with 503 if protection is unavailable; development supports a locked local cache. Exhaustion returns 429 with Retry-After. All ICE endpoint responses, including errors, have Cache-Control: no-store. Limits apply only when issuing credentials, and do not revoke previously issued credentials or change an established peer connection.

Invalid explicitly configured TURN settings now return a redacted 503 even when TURN_REQUIRED is false. Validation rejects partial URL lists, malformed hosts/IPv6/ports, embedded credentials, weak or whitespace/control-containing secrets, invalid policy, and noninteger/out-of-range TTL. Completely absent optional TURN still returns STUN-only configuration. Valid credential format and default one-hour TTL are unchanged.

`CALL_ICE_TRANSPORT_POLICY=all` remains the default. Operators can opt into `relay` with valid TURN settings to hide endpoint addresses from remote peers. This applies to browser/native calls and classrooms. Missing TURN in relay mode fails closed; clients also reject invalid policies and relay responses without TURN before establishing peers. TURN_REQUIRED=true alone does not force relay selection. No production switch was enabled. URL validation cannot prove reachability or secret entropy, and relay-only does not hide users' network metadata from the relay operator.

Call membership, call lifecycle, legacy signaling aliases, recipient authorization and media encryption behavior are preserved. ICE issuance remains account-scoped because clients request configuration before joining; introducing a membership prerequisite would disrupt that flow.

The local runner `scripts/audit_turn_ice_local.py` disables dotenv, configures an in-memory database/cache and runs database-free tests. Its network guard permits only socketpair's internal loopback connect, within a thread-local socketpair creation scope, so Windows asyncio can create its wakeup sockets. Ordinary loopback, external TCP/UDP and DNS attempts remain blocked. Async signaling/origin tests now run successfully under this guard.

Validation completed:

- 37 Python tests passed, covering credential derivation/expiry, validation, optional STUN behavior, relay fail-closed behavior, concurrent per-account throttling, hourly budgets, unavailable production protection, Windows socketpairs, signaling authorization and browser origins.
- 45 Node tests passed, covering web/native call behavior, ICE configuration, relay policy, classroom cleanup and reconnects, native call handling, messaging and diagnostic privacy.
- Targeted diff whitespace checks passed.

No live TURN allocations, production requests, cipher negotiation, browser device calls or native builds were performed. The earlier audit's async-harness limitation and credential validation/throttling findings are addressed by this follow-up; production relay verification remains outstanding.

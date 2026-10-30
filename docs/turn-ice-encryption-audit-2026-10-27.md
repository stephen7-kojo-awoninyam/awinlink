# TURN, ICE, relay privacy and WebRTC encryption audit

Date: 2026-10-27. Scope: checked-out browser/native calls, classroom clients, credential API, configuration validator and coturn reference. Audit only; no deployment or runtime configuration changes. Existing unrelated working-tree changes were preserved.

Follow-up: credential validation/throttling and the Windows async test harness were fixed locally after this audit. See [implementation and verification](turn-ice-hardening-2026-10-27.md). The findings below describe the audited state before those fixes.

## Findings

1. **Medium: peer IP privacy is optional.** `config/settings.py:37-41` defaults TURN off and policy to `all`. `messaging/api_views.py:44-83` returns Google STUN even without TURN. Direct ICE can disclose public network addresses to peers; browser mDNS does not guarantee public-IP anonymity. `TURN_REQUIRED=true` checks configuration, not selected transport. Require policy `relay` as well when peer IP privacy is required. All four browser/native call/classroom paths pass the returned policy to their peer connection. Contrary to the older deployment guide, classrooms now honor this shared policy too.

2. **Medium: authenticated relay abuse surface.** The ICE API requires authentication, but has no call/classroom membership prerequisite or dedicated issuance throttle; REST defaults define no global throttle. Any authenticated account can obtain reusable bearer credentials for the configured lifetime (default one hour). HMAC authenticates the credential; it does not restrict it to a call, recipient, or device. The username contains the numeric account ID, visible to the TURN operator. Add issuance limits and an appropriate active-call/admitted-session eligibility rule; apply relay allocation, bandwidth and egress limits independently. The reference coturn config includes user/total allocation quotas, but these are not evidence of deployed enforcement.

3. **Medium: optional mode bypasses validator errors.** `messaging/api_views.py:52` fails closed only when TURN is required or policy equals `relay`. Otherwise valid URL subsets and any nonempty secret still issue credentials despite errors (short/whitespace secrets, partially invalid URLs, invalid TTL/policy). `messaging/test_call_media.py:18` explicitly covers successful issuance with a short secret and mixed invalid URL. Invalid policy becomes `all`. Reject invalid explicitly configured values consistently; distinguish intentionally absent optional TURN from a broken configuration. No live exploitation was attempted.

4. **Operational: relay isolation remains unverified.** `deploy/turn/turnserver.conf.example` is intentionally incomplete. It enables shared-secret auth, multicast protection and quotas, leaves loopback disabled by default, and asks operators to block private/link-local/metadata destinations at the firewall. Actual ACLs, IPv6 coverage, TLS certificates/protocol versions, clock sync, quotas, port exposure and log retention cannot be established from the checkout. The local validator checks syntax/presence only; it accepts private/internal endpoint names and does not test reachability or secret entropy. Its `production_ready` flag must not be treated as a security or connectivity attestation.

5. **Low: credentials have no client renewal path.** Expiring TURN credentials are fetched when joining. Long calls and later allocation refresh/ICE restart need explicit validation against the provider's expiry behavior. Do not assume expiry necessarily terminates established media at the exact timestamp. Arrange renewal/re-negotiation and secret-rotation overlap before depending on long calls.

## Encryption and metadata boundary

The clients use browser `RTCPeerConnection` and `react-native-webrtc`. WebRTC requires DTLS-SRTP media protection. An ordinary TURN relay forwards encrypted media; `turn:` does not make the media plaintext. `turns:` additionally protects the client-to-relay transport with TLS. Neither hides source IP, connection times or traffic volume from the relay. Awinlink signaling handles SDP, fingerprints and candidates; Google STUN sees discovery traffic in the default configuration. No independent fingerprint comparison, application media-key verification, or insertable-stream encryption was found in the reviewed paths. Peer media is encrypted, but the implementation does not establish independence from a compromised signaling service. HTTPS/WSS termination and negotiated runtime ciphers remain unverified.

Authoritative references: [WebRTC security architecture, RFC 8827](https://www.rfc-editor.org/rfc/rfc8827.html), [IP handling, RFC 8828](https://www.rfc-editor.org/rfc/rfc8828.html), [coturn configuration](https://github.com/coturn/coturn/blob/master/examples/etc/turnserver.conf).

## Controls observed

Authenticated ICE requests; timestamp/user HMAC-SHA1 derived passwords with configurable bounded TTL; shared secret stays backend-side; credential responses and 503s use `Cache-Control: no-store`; relay policy with missing/invalid config returns 503. Call signaling validates schemas and recipient participation; classroom signaling binds messages to active attendance connections. Browser diagnostics are opt-in and native diagnostics development-gated, with metadata allowlists excluding raw SDP, candidates, credentials and IDs. These are source-level controls, not a packet-capture result.

## Safe verification and release gates

Only local mocked client tests and isolated Django validation tests were requested. No production calls, relay allocations, credential requests, port scans, secret changes or deployment actions are authorized by this audit. Tests must not read dotenv; Python checks block outgoing sockets and use only SimpleTestCase classes, with an in-memory database configured as a backstop. Node media tests use mocked peer connections, so cannot prove actual relay selection, IP hiding or cipher negotiation. Browser integration tests may skip without their opt-in harness.

Before a separately authorized release: inspect redacted effective configuration; use two controlled staging devices and synthetic media with relay-only policy; inspect selected candidate types and negotiated DTLS/SRTP stats without exporting raw candidates/credentials; verify failing TURN cannot fall back to direct ICE; test UDP/TCP/TLS and restrictive networks, long-call renewal, clock skew and rotation. Review relay firewall/private destination denial and quotas in operator configuration, without probing internal/metadata addresses from this audit.

Client verification result: node --test tests/call-media.test.cjs tests/call-diagnostics.test.cjs tests/classroom-client.test.cjs tests/classroom-browser.test.cjs: 38 tests, 37 passed, 1 browser harness test skipped, 0 failures. Mocked WebRTC only.

Backend verification: all 9 TURN configuration/credential tests passed in the isolated run. Async signaling checks encountered harness errors because blocking socket.connect prevents Windows asyncio local socket-pair creation; those checks are inconclusive, not application failures. The saved runner now selects only synchronous TURN tests. The default check_turn reported missing URLs/secret and policy all, as expected with dotenv disabled. These are repository defaults, not production values.

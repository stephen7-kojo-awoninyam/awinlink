# Awinlink TURN preparation for Railway

Prepared locally; no Railway variables, services, DNS, firewalls, credentials or deployments were changed. Local TURN URLs and shared secret are absent. Production variables and live relay reachability remain unverified. No secret was generated or displayed.

## Hosting design

Keep Django/ASGI and WSS signaling on Railway. Use a managed TURN service that explicitly supports coturn-compatible timestamp/HMAC-SHA1 credentials, or coturn on an external host with a public IP. A provider that only supplies static usernames/passwords or requires its own credential API needs an adapter; those credentials cannot be pasted into `TURN_SHARED_SECRET`.

Railway documents public HTTP/HTTPS and a raw TCP proxy with an assigned external port. Its private network supports UDP between services, but private addresses are not reachable by browsers and phones on the internet. Based on those documented interfaces, do not assume an ordinary Railway service/TCP proxy can expose the UDP relay range required by this design. A `turn:` URL with `transport=tcp` changes the client-to-relay transport; it does not eliminate the relay's public media-port requirements. Use an external relay unless the platform explicitly provides and validates the necessary public listeners and relay mappings. [Railway TCP proxy](https://docs.railway.com/networking/tcp-proxy), [private networking](https://docs.railway.com/networking/private-networking/how-it-works).

## Variables to prepare

Use [the non-secret Railway example](../deploy/turn/railway.env.example) as the inventory for the Django service, not the mobile build or static frontend.

| Variable | Production value/purpose |
| --- | --- |
| `TURN_SERVER_URLS` | Comma-separated public relay endpoints. Include UDP 3478, TCP 3478 and TLS/TCP 443 if the relay actually exposes those ports. Replace `turn.example.com` with its certificate hostname. No `https://`, embedded credentials, paths or Railway private names. |
| `TURN_SHARED_SECRET` | A unique random secret, at least 32 characters, matching the relay's REST authentication secret exactly. Generate at least 32 random bytes through a password/secret manager and encode as hex or URL-safe text without whitespace. |
| `TURN_REQUIRED` | `true`: invalid/missing relay configuration returns a controlled 503 at the ICE endpoint rather than silently issuing STUN-only configuration. Does not prove network availability. |
| `TURN_CREDENTIAL_TTL_SECONDS` | `3600` by default; validated range 300?86400. Credentials are requested when a call starts. Test the maximum supported call duration; automatic renewal/re-negotiation is not implemented. |
| `CALL_ICE_TRANSPORT_POLICY` | `all` normally. Use `relay` in staging for voice/video tests that must traverse TURN. Web and native call clients honor it; this switch does not configure classroom clients. |

Only the backend holds the shared secret. Authenticated clients receive expiring usernames and derived passwords, not the secret. Treat those short-lived passwords as sensitive too: do not log/copy the raw ICE response, browser network export or WebRTC internals dump into tickets.

On Railway, restrict environment access and seal `TURN_SHARED_SECRET` after storing it securely. Sealed variables are provided to deployed processes but cannot be read back via UI/API or local `railway run`, and are not copied to duplicated/PR environments. Supply staging separately. Prepare values offline now: changing Railway variables can stage a deployment; do not apply/redeploy them as part of this preparation. [Railway variables and sealing](https://docs.railway.com/variables).

## External relay setup for the operator

1. Allocate a public relay hostname/IP near users. Point DNS directly at the relay; do not use an HTTP/CDN proxy. Use a publicly trusted TLS certificate matching the hostname and arrange renewal.
2. Review [the coturn reference template](../deploy/turn/turnserver.conf.example). It is deliberately incomplete and contains no usable credential. Provision `static-auth-secret` privately alongside `use-auth-secret`; coturn does not interpolate `${VARIABLE}` expressions in its config. The backend uses `expiry:user_id` and Base64(HMAC-SHA1(secret, username)), matching coturn REST authentication. Do not enable anonymous authentication. [coturn configuration](https://github.com/coturn/coturn/blob/master/examples/etc/turnserver.conf).
3. Permit inbound UDP/TCP 3478, TCP 443 for TLS, and UDP 49160?49260 for the example relay range. The selected range must match coturn and be large enough for expected allocations. Allow the corresponding egress/return media traffic. If behind NAT, configure its advertised external IP and preserve relay-port mappings. Keep clocks synchronized. [coturn listener and relay options](https://github.com/coturn/coturn/wiki/turnserver).
4. Keep loopback peers disabled. Block relay access to private, link-local and cloud metadata networks at the firewall; preserve public media destinations. Protect the admin interface, secret file and TLS key. Set allocation/bandwidth quotas from expected concurrency and monitor abuse/egress costs.
5. Use distinct production/staging secrets. For rotation, arrange overlap on a relay that supports multiple active secrets; change the issuing backend only after the relay accepts the new one, and retain the old secret for issued-credential lifetime plus clock margin. A single-secret relay requires a coordinated maintenance window. Never use Django `SECRET_KEY` as the TURN secret.

## Redacted verification

Run in the target service's existing runtime environment when authorized (for sealed variables, use a remote shell rather than local `railway run`):

```text
python manage.py check_turn
```

This command performs no network calls or credential issuance. It outputs only configuration booleans, transport coverage, policy, TTL and fixed diagnostic messages; it exits nonzero for invalid production configuration. It does not print URL hosts, input values or secrets. Run it locally now to identify missing values; an expected failure is not permission to substitute a test secret into production.

Before a later approved release, execute this check using the intended service environment. A passing check validates syntax/presence and minimum secret length, not entropy, DNS, certificates, authentication against coturn or relay reachability. Keep TLS/TCP coverage for restrictive networks; the command reports its absence even when UDP configuration is otherwise valid.

The authenticated `/api/messaging/calls/ice-servers/` response is `Cache-Control: no-store`. Missing/invalid configuration in required mode returns 503 with code `turn_unavailable` and `Retry-After: 60`; authentication still applies. Do not add this credential response to a public health endpoint. Apply credential endpoint rate limits and relay quotas appropriate to usage; this preparation does not add account-level abuse throttling.

## ICE diagnostics and acceptance

Use staging with `CALL_ICE_TRANSPORT_POLICY=relay`. Place voice and video calls in both caller directions across browser/browser, browser/native and native/native, on different networks (Wi-Fi/cellular). Require a selected `relay` candidate, increasing inbound audio/video counters and actual audible/visible media. Repeat with UDP blocked to test TCP/TLS fallback, then restore policy `all` for normal use. No live relay probes or two-device calls were made here.

Web: `window.getAwinlinkCallDiagnostics()` returns the latest 100 safe events; `await window.sampleAwinlinkCallStats()` samples counters. Native: filter logs for `[Awinlink call]`. Diagnostics include policy, relay configuration presence, ICE states, selected candidate types, track kinds and inbound byte/frame/loss counters. They exclude shared secrets, derived credentials, SDP and IP/candidate strings.

| Symptom | Operator check / expected handling |
| --- | --- |
| ICE endpoint 503 | Run `check_turn`; inspect variable presence, URL syntax, secret length, TTL and policy privately. Clients stop call setup; web shows a setup error and native displays an alert. |
| Configured relay but ICE fails | Check DNS, advertised public IP, UDP relay range, certificate hostname/expiry and TCP/TLS reachability. `relay_configured` means configured, not reachable. |
| Authentication fails | Check exact secret agreement, REST auth mode, clock skew and expiration. Do not print either secret to compare. |
| Connected but zero inbound media | Check local track attachment/mute state and remote sending/SDP. A signaling connection alone proves no media path. |
| Inbound counters rise but media is absent | Check playback, browser Enable call audio control, OS permission/audio route and native foreground/CallKeep behavior. |
| Disconnected/failed | Existing clients show reconnecting/failed status; automatic ICE restart is not implemented. End and retry after connectivity is restored. |

Read [the media audit](call-media-audit.md) for implementation details. Configuration templates and tests are prepared, not applied. Production readiness still requires privately supplied secrets, a reachable relay and the staged two-device checks above.

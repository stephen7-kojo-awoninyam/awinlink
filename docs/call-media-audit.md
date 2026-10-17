# Voice/video media audit

The web and native clients previously used different signaling payloads. Web emitted `offer`/`answer`, `target_id`, and `ice-candidate`; mobile consumed `description`, `to_user_id`, and `ice_candidate`. They now exchange the latter format, accept legacy inputs, and the server normalizes legacy SDP and recipient fields. Directed signals are delivered only to their recipient.

Both clients serialize SDP/ICE processing, elect the lower user ID to offer, announce readiness after joining, and drain early ICE after either remote description. Local tracks are attached before negotiation. Streamless remote tracks are collected into a MediaStream. Browser remote audio and video explicitly play unmuted; blocked playback exposes a visible Enable call audio button, including for voice calls.

Web now fetches the authenticated ICE endpoint before creating peers, matching mobile. The endpoint returns short-lived HMAC TURN credentials and disables response caching. TURN configuration requires both `TURN_SERVER_URLS` (comma-separated `turn:`/`turns:` URLs) and `TURN_SHARED_SECRET` matching the relay. The local configuration inspected during this audit has neither set. STUN alone cannot provide a relay for restrictive NAT/firewall combinations. No production configuration was inspected or modified.

## Diagnostics

In a web call, run `window.getAwinlinkCallDiagnostics()` for the latest 100 events, or `await window.sampleAwinlinkCallStats()` to sample media counters immediately. Native logs use the `[Awinlink call]` prefix. Both record local track counts, signaling progress, remote track kinds, ICE states, selected candidate types, and inbound byte/frame/loss counters. Stats run every five seconds while peers are active. SDP, candidate strings, IP addresses, media, TURN usernames and credentials are excluded.

No remote track indicates a negotiation/track issue. Failed ICE or no selected pair indicates connectivity; check relay configuration and reachability. A selected `relay` candidate confirms relay selection. Increasing inbound counters with no audible/visible media points to playback or device audio routing. Browser `playback_blocked` events expose the retry button.

## Verification and limits

Regression tests exercise legacy/canonical signaling, recipient routing, deterministic offers, early ICE on both roles, streamless tracks, unmuted playback and retry, TURN validation/credential expiry, diagnostics redaction, cancellation and native call controls. TypeScript and browser JavaScript syntax checks are included.

Device-to-device media, iOS/Android audio routing, real NAT traversal, UDP/TCP/TLS relay reachability and camera playback still need a two-device acceptance test with a working TURN service. Test voice and video in both caller directions across browser/browser, browser/native and native/native, using separate networks and checking for rising inbound counters. These are not established by mocked regression tests. No deployment was performed.

Production setup inventory and redacted validation: [Railway TURN preparation](railway-turn-setup.md).

# Awinlink voice, video, group call and learning room security audit

**Date:** 2026-10-27
**Scope:** Browser and mobile voice/video calls, group call signaling, learning-room media/signaling, ICE/TURN configuration, authorization, and recording privacy.
**Disposition:** Audit and follow-up hardening only. No production configuration, data, or deployments changed.

**Follow-up:** On 2026-10-27, findings 2–4 were addressed in code: call signaling is schema-validated and recipient-scoped, learning-room media defaults off, and call diagnostics are disabled by default and identifier-redacted in development. Finding 1 (production TURN and direct ICE privacy posture) remains an operational verification item.

## Summary

The application uses standard WebRTC peer connections for call media. WebRTC is designed to protect media in transit with DTLS-SRTP; this is transport encryption, not independently verifiable end-to-end encryption. Signaling is carried through Awinlink servers, and the clients do not display or verify peer identity fingerprints. A server or signaling compromise is therefore within the media trust boundary.

Server-side call participation checks and learning-room admission/membership checks are present. Learning-room signaling is substantially constrained and tied to an active attendance connection. The primary issues found are the permissive default ICE policy and unverified production TURN setup, weak message schema enforcement in the general call socket, and learning-room controls that default both camera and microphone to on.

No server-side recording path for calls or learning-room media was found in the reviewed code. The recording features found are explicit voice-message recording controls, which capture a local clip and upload only when the user sends it.

## Ranked findings

| Rank | Severity | Area | Finding |
|---|---|---|---|
| 1 | Medium | TURN and IP privacy | Default configuration permits direct ICE paths and does not require TURN. Production TURN readiness could not be verified from this checkout. |
| 2 | Medium | Call signaling | General call WebSocket relays arbitrary JSON object types/fields after participant checks, without the strict type/field/SDP validation used for learning rooms. |
| 3 | Low | Learning-room capture consent | Camera and microphone both start enabled; pressing Join requests both devices unless the participant first toggles them off. |
| 4 | Low | Diagnostics privacy | Browser call diagnostics are written to the console and retained in a browser-accessible in-memory buffer with call/user/network metadata. |

### 1. Medium — TURN is optional by default; direct ICE may disclose endpoint network metadata

`config/settings.py` defaults `TURN_REQUIRED` to false and `CALL_ICE_TRANSPORT_POLICY` to `all`; TURN URLs and the shared secret default to empty. `CallIceServersAPIView` always returns a public STUN server and adds Coturn REST credentials only when configured. In `all` mode the browser/native peer can select direct host or server-reflexive paths. Those candidates can reveal endpoint network addresses to call peers; TURN relay mode can hide the caller's address from the remote peer, though TURN still observes connection metadata. STUN-only operation can also fail on restrictive NAT/firewall networks.

The endpoint requires authentication but does not check call membership before issuing the short-lived credential. Credentials are HMAC-derived with an expiry and user identifier, and responses are marked `Cache-Control: no-store`, which limits the impact. No application-level request throttle or Coturn quota configuration is visible in this repository; relay resource limits therefore need to be verified at the deployed service.

**Evidence:** `config/settings.py` (`TURN_REQUIRED`, `CALL_ICE_TRANSPORT_POLICY`, `TURN_SERVER_URLS`); `messaging/api_views.py:CallIceServersAPIView`; `messaging/turn.py`; browser call setup in `static/js/main.js`; shared classroom controller in `mobile/src/classrooms/client.js` and generated `static/js/classroom-client.js`.

**Recommended action:** Set and validate production TURN URLs and shared secret; choose `TURN_REQUIRED=true` so a missing TURN configuration fails closed; choose `CALL_ICE_TRANSPORT_POLICY=relay` where hiding peer IP addresses is a product requirement. Use TLS TURN endpoints where supported, set relay allocation/bandwidth/account quotas at Coturn, and rate-limit credential issuance. Verify the effective configuration and real relay connectivity in staging/deployment. Keep `all` only if direct connectivity and its peer-IP exposure are accepted.

The source-level management check reports that it does not itself verify relay reachability. An attempt to run `check_turn` in this checkout stopped during Django startup because the local environment's `SECRET_KEY` failed production-strength validation. No environment settings were changed. Thus neither deployed values nor live TURN reachability are established by this audit.

### 2. Medium — General call signaling lacks a strict message schema

`CallConsumer.receive` bounds frame size, revalidates credentials, and rechecks active call participation. It parses any JSON object, normalizes a few aliases, overwrites `sender_id` with the authenticated user, and relays the remaining object to the call group. It does not enforce an allowlist of client message types, per-type allowed fields, SDP structure/length, candidate length, or a recipient's participation in that specific call before relay. Recipient filtering prevents delivery to unrelated sockets, and frame bounds plus participant checks reduce exposure, but arbitrary signaling payloads can still reach call clients and increase parsing/compatibility risk. In contrast, learning-room signaling uses strict message types, fields and size bounds.

This is not evidence of an unauthenticated call-access bypass: the socket requires an authenticated, active call participant and rechecks that status. The concern is the larger-than-needed signaling protocol surface and client state desynchronization from unexpected messages.

**Evidence:** `messaging/consumers.py:CallConsumer.receive` and `call_signal`; `messaging/socket_security.py`; `learning/classroom_signaling.py` (strict classroom peer-message validation).

**Recommended action:** Adopt a strict call signaling schema with an allowlist for offer, answer, ICE candidate, and required lifecycle events; validate size/shape by type; require target users to be active call participants; keep server-generated lifecycle messages separate from client-relayed events. Add regression coverage for malformed descriptions, unknown types/fields, oversized values, and nonparticipant targets.

### 3. Low — Learning-room Join captures both devices by default

The shared classroom client initializes `camera: true` and `microphone: true`. The web and mobile UIs expose pre-join toggles, but a participant who presses Join without changing them will request both video and audio. Device/browser permission prompts still apply, and participants can turn devices off before joining; the current hint says media is optional. The default nevertheless makes publishing easy to do unintentionally, particularly on mobile.

**Evidence:** `mobile/src/classrooms/client.js` initial state and `join()`; generated browser copy `static/js/classroom-client.js`; web/mobile classroom controls (`static/js/classroom-browser.js`, `mobile/app/classroom/[id].tsx`).

**Recommended action:** Default both devices off, or require a clear pre-join choice that shows which tracks will be published. Keep behavior and labels consistent on web and mobile, and test that default Join requests no media unless the participant opts in.

### 4. Low — Call diagnostics expose metadata through browser console

The browser call client stores up to 100 diagnostic entries in memory and exposes them through `window.getAwinlinkCallDiagnostics()`. It also writes each diagnostic event to `console.info`. Observed fields include call ID, peer/user IDs, signaling message types, candidate types, connection state, media byte/packet/frame counters, and error codes. The inspected diagnostics do not log raw SDP, ICE candidate strings, credentials, or media content, and no server upload was found. Browser consoles may nevertheless persist logs or expose them to local debugging/monitoring tooling.

**Evidence:** `static/js/main.js` (`callDiagnostic`, `recordCallStats`, and signaling diagnostics); native equivalents in `mobile/app/call/[id].tsx` should also be release-log gated.

**Recommended action:** Gate verbose diagnostics behind an explicit development/debug flag, redact identifiers in release builds, and avoid logging signaling details by default. Keep any support export user-initiated and explain what metadata it contains.

## Controls observed

- **WebRTC media transport:** clients use `RTCPeerConnection` / `react-native-webrtc`; no custom plaintext RTP transport was found. The WebRTC security architecture specifies DTLS-SRTP protection for media. This establishes the expected protocol protection, not a runtime proof of negotiated ciphers or independent end-to-end peer identity verification. See [RFC 8827](https://www.rfc-editor.org/rfc/rfc8827.html). TURN relays packets when direct ICE paths fail; see [RFC 5766](https://www.rfc-editor.org/info/rfc5766/).
- **Call access:** call sockets require authenticated credentials and active call participant state, and recheck participation during message handling/delivery. REST call actions are participant-scoped. The ICE configuration endpoint is broader: any authenticated account can request credentials.
- **Learning-room access:** session APIs enforce classroom/course membership and host permissions; learners must be admitted and enrolled. Media join creates an attendance interval, and signaling is tied to the active connection, participant, current membership/admission, and session state. The classroom signaling validator restricts message kinds and bounds SDP/candidates.
- **Cleanup:** inspected web/mobile call and classroom clients stop local media tracks on leave/disposal and tear down peer connections. Mobile learning media leaves when app backgrounds, except while using explicit screen sharing.
- **Recording:** no call or classroom server recorder, call recording API, or call `MediaRecorder` path was found. Web and mobile voice-note controls are explicit; capture is previewed/discardable and upload occurs after the user selects Send. These are messages, not call recordings. Existing message authorization and private media delivery govern access to sent clips. This is a repository search result, not proof that external infrastructure or device-level recording is impossible.
- **Presence/history:** learning-room attendance intervals retain join/leave and connection metadata. They do not contain audio/video recordings in the inspected implementation.

## Audit limits and validation

This was a source review of the checked-out repository. It did not inspect production environment variables, deployed reverse-proxy/WebSocket/TLS configuration, Coturn configuration or quotas, live negotiated WebRTC stats, mobile release builds, or third-party device recording. The `check_turn` management command could not start locally because the configured Django `SECRET_KEY` failed production validation, so production TURN configuration and relay reachability remain unverified. No tests were run because no code was changed and this task requested a documented audit.

# Awinlink mobile release audit

Audit date: 2026-10-17, continued release setup. No deployment, publication, store submission, or production data mutation was performed. An authorized EAS production build was attempted but stopped at authentication before upload/build creation. This is not a release certification.

Launch decision: free at launch; paid features deferred. Both platforms default to `com.awinlink.app`. Availability/ownership is unverified until the owner's Apple and Google developer accounts can check/register it.

## Latest identifier, URL and build verification

- Changed Android package, iOS bundle identifier, draft store metadata, environment example, and server APNs bundle/topic default to `com.awinlink.app`. Existing Firebase files, provisioning profiles, APNs topics and registered store records must match this new identifier; old signing/push configuration must not be reused blindly.
- Read-only production HTTPS checks: `https://awinlink-production.up.railway.app/` returned 200; `/api/feed/posts/` and `/api/messaging/calls/incoming/` returned JSON 401 as expected without authentication; GET `/api/auth/login/` returned JSON 405, confirming the login route exists without creating a session. `/api/` itself returned 404 and is not used as an API health assertion.
- Tested candidate `/privacy/`, `/terms/`, and `/support/` paths returned 404. Actual policy/support environment values are still absent. Do not configure these guessed paths or mark policy availability complete. No production files or server settings were modified.
- Added `npm run check:urls`, a repeatable read-only HTTPS/JSON/status checker. With the real API/web origins it passes those routes and explicitly blocks the three missing policy URLs. Reachability is not evidence of authenticated feature correctness or policy adequacy.
- Android prebuild passed with generated namespace/applicationId `com.awinlink.app`. `android/gradlew.bat :app:bundleRelease --no-daemon` was attempted and stopped: `JAVA_HOME is not set and no 'java' command could be found`. No Android binary was generated.
- iOS prebuild was attempted and skipped by Expo on Windows. Native iOS generation, CocoaPods, Xcode compilation and signing remain unverified.
- EAS `whoami` still reports `Not logged in`; the production build attempt for both platforms again stopped with `An Expo user account is required to proceed.` No remote build or store submission was created.
- Compatible dependency repair updated Expo within SDK 57 (57.0.26 to 57.0.30) and transitive packages. Scoped EAS security overrides retain current major versions: Joi 17.13.8, Ajv 8.18.0, minimatch 5.1.9, nanoid 3.3.20, tar 7.5.22 and yaml 2.8.3. EAS profile resolution is tested through the real EAS schema parser. No forced major-version downgrade was applied.
- Updated-ID regression pass: TypeScript and 38 targeted Node tests passed; 3 backend VoIP/APNs tests passed on isolated SQLite. Real release preflight still correctly blocks unconfigured production environment values. Security findings decreased from 44 to 36 overall (26 high, 9 moderate, 1 low) and from 20 to 19 high in the production dependency tree. Remaining findings are unresolved release risks, not a clean security result.
- Aligned SDK 57 patch dependencies: Expo UI 57.0.25, linking 57.0.13, notifications 57.0.23, router 57.0.28 and splash-screen 57.0.10; added SDK-matched expo-system-ui. Online `expo install --check` passes. Android prebuild passes without the previous system UI warning. The minimatch override is restricted to version 5.1.2 so newer-major consumers keep their APIs; dependency-tree repair and a real oclif-consumer regression check guard EAS command discovery.
- EAS CLI startup now passes (`eas-cli/25.1.1 win32-x64`), all 4 dependency compatibility tests pass, and `npm ls minimatch --all` exits successfully with no invalid resolutions. Explicit compatible minimatch 10.2.6 resolutions preserve the newer oclif/glob APIs. Both Android/iOS Hermes exports and all 47 web routes exported successfully after the SDK alignment; these are unsigned audit artifacts in ignored `dist-audit/`, not native store builds.
- Final combined targeted Node run: **39 passed, 0 failed**. No deployment or publication occurred.

## Implemented repairs

- Shared token refresh across simultaneous requests, persisted rotated refresh tokens, and refused stale refresh responses after sign-out.
- Protected authenticated routes, including direct links to conversations, calls, learning, and organization workspaces.
- Added feed image/video attachment selection and multipart posting; added comments, ownership-aware deletion, and duplicate-like suppression.
- Fixed backend comment read/write visibility enforcement and non-string comment validation.
- Added focused conversation polling and foreground refresh, with request fencing and preservation of messages sent during a refresh.
- Stopped incoming-call polling in the background, fenced timer creation after logout, and reset handled-call state between sessions.
- Added course lesson video playback and note-file links; replaced invalid lesson URL/text submissions with actual multipart file uploads.
- Fixed backend multipart lesson parsing and returned completed lesson IDs so completion survives reopening a course.
- Added the organization owner team screen for invitations, revocation, member roles, suspension, restoration, and removal. Invitation secrets use URL fragments, matching the existing web response flow.
- Added alert links to conversations/opportunities, organization website actions, and back navigation on secondary pages.
- Replaced generic app naming/scheme with Awinlink; added SecureStore backup configuration, build versions, EAS profiles, and production environment validation. Removed duplicate audio plugin registration.
- Repaired incomplete installed Expo UI source files and pinned the matching dependency in package.json/package-lock.json.
- Added native password-reset request/confirmation, single-use Django reset tokens, recovery throttling, and token revocation after password changes. Invalidated sessions now leave authenticated navigation.
- Added password-confirmed account deletion. Owners must transfer their organization first; deletion removes the account and cascaded database content. Moderation reports retain their content with the reporter relation removed; storage/backup retention still needs operator verification.
- Added report screens and a staff moderation queue, block/unblock settings, profile/post/message reporting, bilateral blocking enforcement for messages/calls/follows/connections/comments/likes, and blocked profile/feed filtering. Blocking ends affected active calls and denies signaling.
- Added native invitation acceptance/decline (including sign-in within the invitation flow), app invitation links, and confirmed ownership transfer. Removed stale owner controls after permissions change.
- Fixed the web messaging global-search assertion by making mobile global search available on the conversation list.
- Fixed browser helpers: direct FFmpeg fixture generation, quieter browser startup, sequential headless Edge checks, and bounded startup timeouts. Both browser checks now pass.
- Added scoped UUID 11.1.1 for Xcode generation and a licensed CommonJS adapter of upstream decode-uri-component 0.5.0. Tested the actual Xcode/query-string consumers, including adversarial malformed URI input. Framework versions remain unchanged.
- Completed environment-driven release configuration for policy/support URLs, app identities, matching Android FCM files, iOS production push entitlements, signing profiles, and removal of legacy storage/overlay permissions from production.
- Replaced Expo starter artwork with repository-owned Awinlink monogram assets and added draft store text/data-disclosure worksheets under `mobile/store/`.
- Prevented paid-course enrollment bypass while billing is unconfigured, redacted unenrolled paid lesson assets, and made purchase unavailability explicit. No payment is initiated by this build.

## Verification evidence

Call cancellation repair: caller cancellation now transitions the call/participants under a row lock, marks incoming notifications read, and publishes `call_ended` after commit to the call room **and both users' global sockets**, including a recipient who has not answered. End requests are idempotent; acceptance cannot revive a terminal call. Last-recipient decline, ringing timeout and caller signaling disconnect use the same terminal notification path. New call creation is serialized per conversation. Locks on joined queries target only the call row, avoiding nullable-join locks and conversation/call lock-order inversion on PostgreSQL.

Web and mobile release local audio/video, peers, sockets and timers before waiting for the API. Operation generations prevent late media permission, start/accept replies and old socket callbacks from reviving or clearing another call. Redial waits for outstanding cancellation mutations instead of racing the old ringing row. Mobile incoming fallback uses a dismissible app modal instead of a native alert that cannot be programmatically removed. Global terminal events close CallKit/Telecom and matching presented notifications; stale events are scoped by call ID.

Cancellation validation: broader isolated backend run **54 passed**; focused final API/expiry/disconnect/decline run **18 passed**; targeted Node run **46 passed** before two additional cancellation tests; latest cancellation/native-call rerun **12 passed**, covering caller and recipient, delayed end/start/accept, permission prompts, timer expiry and immediate redial. TypeScript and web JavaScript syntax checks pass. These tests execute the real web functions and transpiled mobile screen with controlled media/transport mocks, plus real isolated Django API transitions. They do not constitute physical-device tests or a PostgreSQL concurrency stress test. Background/terminated-device cancellation delivery and platform audio teardown still need a real Android/iPhone acceptance pass. No deployment was performed.

Latest native-call pass: TypeScript passed after replacing an unsupported CallKeep settings method; 36 targeted Node tests passed in the combined run. Notification/VoIP backend tests: 20 passed against isolated SQLite; the 3 Expo call-delivery tests also passed afterward, including the added Android data-only regression (overlapping counts). Android `expo prebuild --no-install --platform all` passed, and the generated manifest includes the custom Firebase service, Telecom service and phone-call foreground-service permission. Explicit iOS prebuild is skipped by Expo on Windows and exits unsuccessfully; iOS native generation/compilation remains unverified. Final Android/iOS Hermes and web exports passed into ignored `dist-audit/` before the last incoming-call activation adjustment; exports are audit artifacts without production configuration. Real release preflight correctly exits with `BLOCKED Set EXPO_PUBLIC_API_URL to a valid HTTPS URL.`

Call integration now includes native CallKit/PushKit startup before React, Android Telecom with a data-message Firebase service, cold-start event replay, authenticated answer validation, duplicate/expired call handling, mute/hold/end controls, and media-acquisition cleanup fences. Backend PushKit token ownership and APNs HTTP/2 transport are implemented. These source changes still require native compilation and physical-device acceptance before being considered release-ready.

| Check | Result |
| --- | --- |
| TypeScript (`tsc --noEmit`) | Passed |
| API-client, dependency adapters, production-config, media, classroom-controller Node tests | 33 passed, including the final late-refresh/new-login regression |
| Classroom API/security/signaling/interfaces/notifications, organization-team API, comment backend tests | 135 tests: 131 passed, 4 skipped |
| Course moderation plus new lesson-upload/progress and comment regressions | 11 passed |
| Final focused lesson-upload/progress and comment regressions after last edits | 5 passed |
| Broad account/API/messaging/signaling/feed/learning/organization/notification run | 118 passed; previous web-template failure fixed |
| Latest focused accounts, paid lessons, course moderation, comments, organization-team and signaling run | 56 passed |
| Android and iOS Hermes production bundle export | Passed for both platforms; artifacts in ignored `mobile/dist-audit/` |
| Expo native config introspection | Passed for Android and iOS; camera/microphone permission descriptions verified |
| Django system checks / migration drift / git whitespace | Passed; no additional model migrations missing |
| Production config with synthetic identifiers/FCM fixture | Passed, including rejection of bad URLs and mismatched FCM package; real preflight correctly blocks missing environment |
| Real browser checks | 2 passed in headless Edge: classroom controls/mobile viewport plus actual audio recording/video playback at 1440px and 390px |

Test runs overlap; do not add these counts as unique tests. Backend checks use an isolated in-memory SQLite database and in-memory Channels layer, not production services. The two real browser checks run separately from the targeted Node suite. Hermes exports were run without real API environment values and are audit artifacts only; rebuild with production configuration before signing or distribution.

## Release configuration

Set these in the build environment using real, owned values:

```text
EXPO_PUBLIC_API_URL=https://your-api-origin
EXPO_PUBLIC_WEB_URL=https://your-web-origin
EXPO_PUBLIC_EAS_PROJECT_ID=your-existing-eas-project-uuid
AWINLINK_ANDROID_PACKAGE=com.awinlink.app
AWINLINK_IOS_BUNDLE_IDENTIFIER=com.awinlink.app
AWINLINK_APPLE_TEAM_ID=your-apple-team-id
AWINLINK_GOOGLE_SERVICES_FILE=path-to-your-google-services-file
EXPO_PUBLIC_PRIVACY_URL=https://your-web-origin/privacy
EXPO_PUBLIC_TERMS_URL=https://your-web-origin/terms
EXPO_PUBLIC_SUPPORT_URL=https://your-web-origin/support
```

The `EXPO_PUBLIC_*` values ship in the bundle. Signing keys, TURN secrets, and backend secrets must remain outside it.

Run from mobile/:

```text
npm ci
npm run typecheck
npm test
npm run check:release
npm run check:urls
npm run export:android
npm run export:ios
```

`check:release` loads Expo environment files and validates production configuration. Android requires a matching FCM file; for an iOS-only preflight set `EAS_BUILD_PLATFORM=ios`. It never uploads credentials. Public URLs must exist and accurately describe the real service; tests use synthetic fixture URLs only.

Prepared EAS profiles: preview Android APK/iOS simulator, preview-device for a signed physical iPhone, and production Android AAB/iOS store archive with remote version increments. EAS CLI 25.1.1 is pinned locally. After authenticating with `npx eas login` and linking the correct existing project, configure the environment above and provision signing credentials, then run `npm run build:android`, `npm run build:ios`, or `npm run build:device`. Production commands freeze credentials so missing signing material stops the build. `.easignore` excludes generated native folders, local environment files and signing secrets while retaining the reproducible native config plugins. Supply the Android Firebase file through the EAS file environment variable. No submit command or auto-submit option is included. See [Expo EAS configuration](https://docs.expo.dev/eas/json/) and [Expo authentication](https://docs.expo.dev/accounts/programmatic-access/).

Actual attempted command: `node node_modules/eas-cli/bin/run build --platform all --profile production --non-interactive --no-wait --freeze-credentials`. Result: `An Expo user account is required to proceed.` No build IDs, AAB or IPA were produced.

## Remaining blockers and incomplete workflows

1. This Windows environment has no Java, adb/Android SDK or Xcode. EAS CLI is installed but not logged in. No native emulator/device run, signed AAB or IPA has been produced. JavaScript/Hermes exports are not native builds or device tests.
2. `com.awinlink.app` is configured for Android/iOS, subject to developer-account availability. EAS project UUID, actual service/policy URLs, FCM file and signing credentials are missing; production configuration deliberately fails without required environment values.
3. CallKit/PushKit and Android Telecom source integration is implemented, but native compilation, terminated/locked-device calls and APNs/FCM delivery are unverified. HTTPS/WSS, Redis/Channels, TURN across separate networks, and production storage still need integrated verification.
4. The latest online `npm audit --omit=dev` reports 19 high, zero moderate/critical findings. The production dependency chains trace to [braces GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) and [node-forge GHSA-86w9-cpqp-85rv](https://github.com/advisories/GHSA-86w9-cpqp-85rv). Registry checks earlier in this audit reported braces 3.0.3 and node-forge 1.4.0 as latest, both within the advisory ranges. Safe compatible updates and scoped EAS fixes reduced the complete tree from 44 to 36 findings (26 high, 9 moderate, 1 low); remaining development roots include diff, sprintf-js, ts-deepmerge and older UUID consumers. These require further remediation or an explicit release risk decision; no forced framework downgrade was made.
5. Browser helper failures are resolved; both checks pass. This verifies Chromium behavior, not Safari or native Android/iOS WebRTC.
6. The web messaging regression is resolved and the broader 118-test run passed.
7. Awinlink monogram icons/splash and store descriptions are prepared. Real signed-build screenshots, public policy/support/deletion pages, age/content declarations, final artwork review, and actual data-use disclosures remain operator/store tasks. See `store/metadata.json` and `store/DATA_INVENTORY.md`.
8. Free launch is configured (`launch.free=true`, `purchasesEnabled=false`); course authoring always submits free courses and the unfinished advertisement creation option is removed. Existing paid courses remain guarded against enrollment/asset bypass. Paid features and native billing are deferred and must be implemented and verified before purchases are offered. See [Apple's digital purchase guidance](https://developer.apple.com/app-store/review/guidelines/#business).
9. The app's screens have not received a full physical-device accessibility, keyboard, tablet, offline, or performance pass. Backend automated coverage does not replace it.

## Backend rollout notes (not executed)

`notifications/migrations/0011_voip_push_tokens.py` must also be applied in an authorized backend rollout. Install the pinned `httpx[http2]` dependency. Configure server-only `MOBILE_APNS_TEAM_ID`, `MOBILE_APNS_KEY_ID`, `MOBILE_APNS_PRIVATE_KEY` (APNs .p8 contents), and `MOBILE_IOS_BUNDLE_ID=com.awinlink.app`; never put these in EXPO_PUBLIC variables or commit the key. Production and internal-distribution devices use production APNs; local development uses sandbox. Successful native delivery suppresses the paired Expo fallback. Test both transports on real devices, including disabled Android phone-account and notification permission paths.

`accounts/migrations/0005_mobile_safety.py` creates blocks and content reports. It must be applied to the server before the new safety screens are used. Only isolated test-database migrations ran here. `SIMPLE_JWT.CHECK_REVOKE_TOKEN` and the custom refresh serializer require users with older JWTs to sign in again and reject sessions after password resets/account deletion. Do not apply this change to a live service until a deployment is explicitly authorized. Staff must operate the ContentReport admin queue; creating a queue does not establish a moderation response SLA.

## Updated completion checklist

- [x] Native password recovery and account-deletion screens/APIs with password/token validation.
- [x] Content reporting, staff queue, bilateral blocking, and unblock settings.
- [x] Native organization invitation responses and ownership transfer.
- [x] Web messaging regression fixed; broad backend test run passed.
- [x] Real Chromium classroom and media browser tests pass.
- [x] Safe UUID and URI-decoder remediation with compatibility tests; no forced framework changes.
- [x] Android/iOS bundle exports and production-config regression checks.
- [x] Native release profiles, FCM/APNs configuration hooks, monogram assets, and store metadata drafts.
- [x] Configure requested Android/iOS identifier `com.awinlink.app`, subject to availability.
- [x] Verify real production origin/API route reachability; missing policy pages recorded as blockers.
- [x] Apply compatible SDK/tooling security updates; validate EAS schema, CLI startup and dependency resolutions.
- [ ] Supply working privacy, terms and support URLs (tested candidate paths return 404).
- [x] Configure free launch and defer paid offerings.
- [x] Implement CallKit/PushKit and Android Telecom source integration and regression checks.
- [x] Install/pin EAS CLI and attempt production builds without submission.
- [ ] Authenticate Expo, confirm identifier availability, and supply EAS project, policy URLs, push files and signing credentials.
- [ ] Resolve the two remaining upstream advisory roots or document an explicit release risk decision.
- [ ] Compile and verify CallKit/Telecom on physical devices, including locked/terminated states.
- [ ] Verify SMTP recovery delivery, moderation operations, deletion/media retention, push, TURN, WSS, Redis and storage in an authorized test environment.
- [ ] Compile/sign AAB and IPA and complete physical Android/iOS acceptance tests.
- [ ] Capture real store screenshots and finalize store disclosures/review accounts.
- [x] No deployment or publication performed.

## Required native acceptance pass

Run on both a supported Android phone and iPhone, using separate test accounts and isolated test data:

| Area | Scenarios |
| --- | --- |
| Authentication | Register, login, restart session, simultaneous expired-token requests, revoked refresh token, sign-out and protected deep links |
| Feed | Empty/error/retry, image/video post, playback, rapid likes, comments, private-post denial, own-comment deletion |
| Messaging | Direct/group conversation, new incoming messages, text/file/image/video/voice, background/resume, read state, upload failure |
| Calls | Voice/video both directions, permissions denied, answer/decline push, cold launch, expired ringing, reconnect, TURN on separate networks, background cleanup |
| Learning | Enroll, video/notes, completion across restarts, quiz/results/certificate, author lesson files, submit/moderate course |
| Organizations | Browse/follow/edit, owner roster, invite/share/respond, role change, suspend/restore/remove, revoked permissions |
| Notifications | Foreground/background/terminated delivery, permission denial, mark one/all read, conversation target, sign-out token removal |
| Other screens | Opportunities/applications, connections, portfolios, events/certificates, competitions, shortlists, recruitment and specialist workspaces |

Record device/OS/build number and evidence for each case before declaring the app complete or store-ready.

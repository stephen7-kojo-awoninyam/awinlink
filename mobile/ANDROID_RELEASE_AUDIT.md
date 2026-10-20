# Android release audit — October 19, 2026

Status: **blocked for APK creation and Play Store release**. No backend deployment, production environment edit, EAS Update, store submission, paid plan upgrade, or signing-key rotation was performed. This is the latest Android audit; October 17 reports retain their historical results.

## Prepared locally

- Added `android-apk` in `eas.json`: internal distribution, standalone release APK, preview environment, medium worker, existing remote signing credentials. It embeds the existing public Railway API origin and public policy links. It does not increment versions or change the production AAB profile.
- Added `npm run build:android:apk`. `--freeze-credentials` prevents silently generating/replacing signing material. A missing key must be resolved deliberately by the account owner.
- APK configuration rejects missing/insecure API origins, common localhost/private development addresses, `/api/` suffixes, missing public policy links, missing EAS project UUID, and missing/mismatched Android Firebase client configuration.
- APK permissions match the production restriction on overlay access; legacy broad storage access remains blocked. Firebase client files and generated APK/AAB/IPA artifacts are excluded from the EAS source archive. Supply Firebase via an EAS file variable, rather than committing it.
- Added executable regression tests for APK configuration and profile behavior.

## Audit findings

| Area | Evidence and remaining gate |
| --- | --- |
| Identity | `com.awinlink.app`, version `1.0.0`, local versionCode `1`. Availability, ownership and existing Play version history require the owner's console. Production versions are managed remotely; do not assume local versionCode is the final store version. |
| SDK | Installed Expo `57.0.30`, React Native `0.86.3`. React Native's Gradle defaults target/compile API 36, minimum 24. Google currently requires API 36 for new phone-app submissions. Verify the final artifact, native dependencies and 16 KB page alignment after a successful native build. |
| Production API | Read-only HTTPS checks passed: `/` 200; `/api/feed/posts/` and `/api/messaging/calls/incoming/` JSON 401; GET `/api/auth/login/` JSON 405. These establish reachability and unauthenticated access control, not authenticated feature correctness or outstanding migrations. No production account/data was created or changed. |
| Public policies | `/privacy/`, `/terms/`, `/support/`, `/delete-account/` now exist, but all fail the release URL checker because operator/contact configuration is incomplete. This supersedes the October 17 finding of 404 responses. Operator must review legal identity, monitored support, retention and actual data handling; any production configuration changes require approval. |
| API security | Client appends `/api/` to its configured origin, uses SecureStore for account tokens and WSS for HTTPS origins. Media credentials are limited to the API's own protected `/media/` URLs. Authenticated uploads, account recovery/deletion, role permissions and calls still need production test-account acceptance. |
| Permissions | Direct camera/microphone/audio permissions support calls, recordings and classrooms. Expo Notifications contributes `POST_NOTIFICATIONS`; runtime code creates a channel before requesting permission. Calling dependencies also contribute `CALL_PHONE`, `READ_PHONE_STATE` (through API 29), `READ_PHONE_NUMBERS`, and Telecom access. Foreground-service declarations include phoneCall and mediaProjection. Review these in the final merged manifest and complete applicable Play foreground-service declarations. Do not remove Telecom permissions without testing native calls. No broad photo-library permission is explicitly requested by app config; verify transitive merged permissions. |
| Notifications | Android channel/category, permission request, token registration and custom Firebase incoming-call service exist. Firebase client file, real EAS project ID and FCM v1 service-account credential in EAS are not supplied/verified. Client `google-services.json` is distinct from the private FCM service-account key. Background/terminated/locked-screen delivery, token rotation, cancellation and Android permission denial require physical devices. Foreground WebSocket fallback does not prove background delivery. |
| Signing | Remote release/upload keystore and certificate fingerprints are unverified because EAS is not authenticated. Ignored generated local Gradle uses the standard debug signing template; that is not proof of a release-signed APK. EAS must inject the owned release credentials. Preserve the existing upload key if the Play app already exists. Play App Signing enrollment is unverified. |
| Dependencies | Fresh online `npm audit --omit=dev`: **19 high**, zero critical/moderate/low. Root advisories are braces stack-exhaustion and node-forge RSA signature verification; other findings propagate through their dependency chains. Both advisories list no patched release at this audit. npm's suggested Expo 44 downgrade is incompatible with this SDK and was not applied. Audit includes Node build tooling; it does not establish that all findings are reachable in the Android runtime. Resolution or an explicit exposure assessment remains required. Raw local output: ignored `audit-android-production.json`. |
| Store readiness | Existing store metadata and data inventory remain drafts. Verify Data Safety, content/age ratings, social-app moderation/safety operations, public account deletion, reviewer accounts, screenshots, package ownership and Play account testing requirements. Purchases stay disabled. An APK is for direct device testing; the existing production AAB profile is the eventual Play upload format. |
| Local native fallback | Java/JDK and adb/Android SDK are unavailable on PATH. This Windows environment cannot currently provide a local native-build or device-install fallback. |

## Verification

- Existing mobile Node suite: **84 passed, 2 skipped, 0 failed** (86 total). Browser/device acceptance is not covered by the skipped tests.
- APK and existing production configuration tests: **4 passed, 0 failed** (two new APK tests plus two existing release tests).
- TypeScript: `npm run typecheck` passed.
- Installed EAS schema resolver accepted the new profile and resolved internal distribution, preview environment, APK output, medium worker, remote credentials and `developmentClient: false`.
- Offline Expo dependency alignment check: passed, with Expo's warning that offline validation is less reliable than an online check.
- Production URL checks: four API/web checks passed; four policy/completion checks blocked as described above.
- `npm run check:release` blocks the absent production API environment, while asset/profile/SecureStore checks pass. APK-specific local config evaluation blocks the absent owned EAS project UUID. No environment values were invented to pass these gates.
- EAS `whoami`: **Not logged in**. Attempted `eas build --platform android --profile android-apk --non-interactive --no-wait --freeze-credentials`; it exited with **An Expo user account is required to proceed**. No build ID, queued cloud job, APK or download URL was created. Account plan/quota and remote signing remain unverified.
- Android Hermes export: **passed** outside the sandbox, 1,444 modules, 27 assets and a 3.5 MB Hermes bundle in ignored `dist-audit/android-release/`. The initial sandbox attempt denied execution of Hermes; the permitted retry succeeded. This verifies JavaScript bundling, not native compilation, signing, device behavior or an installable APK.

## Finish the free APK build

1. From `mobile/`, sign in locally with `npx.cmd eas login`, then verify `npm.cmd run eas:whoami`. Do not send passwords or Expo tokens in chat.
2. Identify the owner's existing EAS project. Set `EXPO_PUBLIC_EAS_PROJECT_ID` to its UUID locally and in the **preview** environment. Verify access with `npx.cmd eas project:info`. Confirm ownership of `com.awinlink.app`; do not register a replacement identity or rotate an existing key.
3. Supply matching `google-services.json` using `AWINLINK_GOOGLE_SERVICES_FILE` locally for config evaluation and an EAS file variable in preview. Configure the corresponding FCM v1 service-account credential through the owner's EAS credentials UI. Never bundle the private service-account key or put it in `EXPO_PUBLIC_*`.
4. Confirm the account is on the Free plan with an Android build remaining. Expo currently lists 15 Android builds/month on Free and a low-priority queue. If the quota is exhausted, wait for renewal; no upgrade or paid usage is authorized.
5. Verify the existing Android remote signing credentials. If none exist, the owner must establish and securely retain the appropriate key before the frozen-credential build can proceed.
6. Run `npm.cmd run build:android:apk`. Do not add `--auto-submit`. Save the returned EAS build ID, logs and APK download URL. Download the completed APK and record its SHA-256, package/version, signing certificate, target SDK, merged permissions and 16 KB compatibility. No build ID or download URL should be invented when authentication/configuration fails.
7. Install on physical Android devices and test cold launch, login/refresh/logout, role restrictions, feed/posts/media, opportunities/courses/organizations, messaging, denied permissions, notifications in foreground/background/terminated states, lock-screen calls, cancellation, TURN across networks, account deletion and offline recovery. Use designated test accounts. Record actual device models/OS versions and results before approving release.

Public-page completion, backend service configuration and any deployment remain separate approval-dependent work.

## References

- [Expo APK build and installation](https://docs.expo.dev/build-reference/apk/)
- [Expo Free plan and build quota](https://expo.dev/pricing)
- [Expo Android FCM credentials](https://docs.expo.dev/push-notifications/fcm-credentials/)
- [Google Play target API requirement](https://support.google.com/googleplay/android-developer/answer/11926878)
- [Android 16 KB page-size verification](https://developer.android.com/guide/practices/page-sizes)
- [Google Play account deletion](https://support.google.com/googleplay/android-developer/answer/13327111)
- [braces advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm)
- [node-forge advisory](https://github.com/advisories/GHSA-86w9-cpqp-85rv)

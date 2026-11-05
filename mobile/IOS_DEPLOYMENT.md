# iOS deployment handoff

This is preparation only. No commit, push, remote build, deployment, TestFlight upload, or App Store submission was requested or performed.

## Local validation (2026-10-31)

- `npm run typecheck`: passed.
- `npm test`: 235 tests, 232 passed, 3 skipped, no failures after SDK updates. Includes iOS APNs environment, CallKit-to-WebRTC audio activation, device-bound credential accessibility, Add person submission, and Android APK/release regressions.
- Expo configuration introspection: passed, including the production iOS configuration. The resolved config contains production APNs, `voip`/`audio`/`remote-notification` background modes, camera/microphone descriptions, disabled bitcode, and disabled arbitrary HTTP loads. SDK compatibility check identified and prompted updates to Expo 57.0.31, Expo UI 57.0.26, notifications 57.0.24, and router 57.0.29; the lockfile is updated. The final online `npx expo install --check` passed with no SDK version mismatches. This check does not validate third-party native call modules against Xcode.
- iOS native prebuild: unavailable on Windows (details below). CocoaPods and Xcode compilation were not run.
- JavaScript exports for iOS and Android were attempted, stalled in this workspace, and stopped. These are incomplete checks, not passing bundle results.
- Initial SDK installation reported 13 npm advisories (2 low, 11 moderate); this was not a comprehensive security audit. Local dev-tool restoration used cached packages with install scripts disabled after an optional `dtrace-provider` build stalled. Normal native builds still need their normal dependency installation and CocoaPods steps.

Local output logs: `audit-ios-tests-verified.log` and `audit-ios-production-config.json`. Generated audit files are ignored by Git.

## Configuration

- App identity: Awinlink, `com.awinlink.app`, version 1.0.0. Confirm ownership of this bundle identifier before signing. Override with `AWINLINK_IOS_BUNDLE_IDENTIFIER`; set `AWINLINK_APPLE_TEAM_ID` for your team. Keep store metadata and the backend APNs topic aligned with any override.
- The existing 1024px branded icon and branded splash are used by Expo. Expo strips icon transparency when generating iOS icons; the splash plugin generates the native launch screen.
- Camera and microphone purpose strings cover video calls, classrooms, and voice messages. Add person invites by username through the authenticated backend and does not need Contacts permission. Document picking uses the system picker.
- CallKit/PushKit native startup, `voip`, `audio`, and `remote-notification` background modes, and APNs entitlements are configured through the existing native call plugin. WebRTC now receives CallKit audio session activation/deactivation events.
- Native authentication storage uses device-bound Keychain accessibility after first unlock so authenticated CallKit actions can work while locked. Existing installs should sign in again to rewrite old tokens with this accessibility. Calls before the first unlock after reboot still require unlocking.
- APNs routing uses `extra.apnsEnvironment` from the same configuration as the entitlement. EAS profiles default to production APNs; local Xcode development defaults to development. Use `AWINLINK_APNS_ENVIRONMENT` only to match an actual different signing profile. JavaScript `__DEV__` does not determine APNs routing.
- Production configuration disables arbitrary HTTP transport. Preview can use LAN development endpoints. Use public HTTPS API/web origins for physical-device release testing.
- EAS `ios-simulator` creates an unsigned simulator build; `ios-device` creates an internal distribution build for registered devices; `production` remains a store distribution profile. Android profiles and permissions are retained. `.easignore` excludes native directories so cloud builds regenerate them from config plugins.
- Native WebRTC, CallKeep and VoIP push packages require a custom native binary. Expo Go cannot validate this app's call stack. Existing legacy native modules still require an actual CocoaPods/Xcode compilation against React Native 0.86; JavaScript bundling and config introspection cannot establish native binary compatibility.

## Account and signing requirements

1. Own or have access to the configured EAS project. Set the production/preview EAS environment values from `.env.example`, including HTTPS endpoints and `EXPO_PUBLIC_EAS_PROJECT_ID`. Never place signing keys or TURN secrets in public app variables.
2. For signed EAS device/store distribution, use an Apple Developer Program team with permission to register the explicit App ID, enable Push Notifications, and manage distribution certificates/provisioning profiles. Internal distribution needs each test device UDID included in the provisioning profile. Configure credentials separately before using the existing `--freeze-credentials` production script.
3. Configure the APNs key for Expo notification delivery in EAS. Separately configure the backend's direct VoIP APNs credentials (`MOBILE_APNS_TEAM_ID`, `MOBILE_APNS_KEY_ID`, `MOBILE_APNS_PRIVATE_KEY`) and `MOBILE_IOS_BUNDLE_ID` in `config/settings.py`. The topic must match the bundle ID plus `.voip`; environment must match the signed app. An Expo push token alone does not enable PushKit delivery.
4. A Mac with supported Xcode and CocoaPods is required for local iOS compilation/simulator work. EAS can compile on its macOS workers when invoked from Windows, but no remote build was started in this task.

References: [Expo signing credentials](https://docs.expo.dev/app-signing/app-credentials/), [iOS capabilities](https://docs.expo.dev/build-reference/ios-capabilities/), [push setup](https://docs.expo.dev/push-notifications/push-notifications-setup/), [EAS iOS build process](https://docs.expo.dev/build-reference/ios-builds/).

## Remaining native acceptance checks

On macOS, generate iOS with `npx expo prebuild --platform ios` and compile with `npx expo run:ios`, or explicitly authorize an EAS simulator/device build later. A local `prebuild --platform ios --no-install` was attempted on Windows: Expo explicitly skipped iOS generation and exited with "At least one platform must be enabled when syncing". Verify CocoaPods resolution, Swift bridging header, Objective-C compilation, native module autolinking and the final signed entitlements. Do not disable the new architecture to hide native dependency problems; React Native 0.86 requires compatibility to be proven with this toolchain.

Use physical iPhones (and an iPad because tablet support is enabled), plus an Android counterpart:

- Check icon, cold-launch splash, navigation/safe areas, login/logout, system document picker, notification permission denial and re-enabling from Settings.
- Grant/deny camera and microphone independently. Test voice/video, mute, camera toggling/switching, speaker/earpiece/Bluetooth routing and interruptions from another system call.
- Test incoming calls while foregrounded, backgrounded, locked and cold started; answer/decline through CallKit; check stale push expiry, hangup, and logout token removal. Explicit user force-quit has OS delivery limitations and needs separate observation.
- Add person with the iOS keyboard open; verify trimmed usernames, pending submission, permission/unknown-user errors, successful invite, guest accept/decline, multiple remote streams and hangup cleanup. Existing backend invitation changes must be included in the eventual backend release.
- Exercise Wi-Fi/cellular and forced TURN relay between iOS and Android. Configure authenticated TURN on the backend; STUN-only success on one LAN is insufficient evidence for deployment.
- Review privacy disclosures, purpose strings, export-compliance declaration, store screenshots and any third-party authentication requirements before future submission.

No signed binary, account ownership, APNs delivery, native compilation or physical-device behavior is certified by local TypeScript/config/tests.

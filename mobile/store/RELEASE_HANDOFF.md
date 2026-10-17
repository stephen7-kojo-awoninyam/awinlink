# Awinlink store release handoff — October 17, 2026

Status: blocked for release. No publishing, store submission, deployment or production database mutation is authorized by this handoff. Prepared EAS production profiles build signed Android AAB and iOS archives using remote credentials; they do not submit to stores.

## Required accounts and access

| Account | Required access / material | Current verification |
| --- | --- | --- |
| Expo / EAS | Owner's account or organization, existing project UUID, permission to build and manage credentials, available build quota | CLI reports `Not logged in`; project UUID is absent |
| Apple Developer Program | Active membership, registered `com.awinlink.app`, team ID, distribution certificate and App Store provisioning profile | Ownership and signing unverified |
| App Store Connect | App record, role permitting app management, agreements, review contact and demo accounts | Unverified; no submission performed |
| Google Play Console | Verified developer account, available `com.awinlink.app`, app record, Play App Signing enrollment and retained upload key | Unverified; no submission performed |
| Firebase / Google Cloud | Android app matching `com.awinlink.app`, google-services.json, FCM v1 credentials configured in EAS | Not supplied |
| Backend hosting (current Railway service) | Authorized operator access to deploy pages/migrations and configure HTTPS, storage, SMTP, Redis, TURN, APNs | Only public routes checked; no service configuration inspected |
| Public support mailbox | A monitored mailbox and legal operator identity | Not supplied; configure `AWINLINK_SUPPORT_EMAIL` and `AWINLINK_LEGAL_OPERATOR` |

Keep passwords, Expo tokens, signing keys, APNs .p8 keys and FCM service-account keys out of Git and chat. Authenticate in the local CLI or provider dashboard. A Google Play service account is unnecessary for build-only work. An App Store Connect API key is optional; do not create submission credentials just to build.

## Public pages and backend rollout

Implemented `/privacy/`, `/terms/`, `/support/`, `/delete-account/`, and a browser sign-in/deletion flow. The deletion form requires a session, CSRF token, current password and explicit confirmation. Organization owners must transfer ownership first. Browser deletion uses the same database deletion behavior as the mobile API; physical media/backup erasure remains unverified.

All four public URLs still return HTTP 404 on production. `mobile/.env.example` and `metadata.json` contain **planned** URLs, not evidence of deployment. Do not use them in a store listing until deployed and checked. Public pages visibly flag missing operator/contact configuration and `npm.cmd run check:urls` rejects that incomplete state. The privacy text still requires operator confirmation of storage providers, retention periods, deletion cleanup, jurisdictions and actual data practices. Terms require owner review as well.

Backend operator must apply outstanding migrations (including account safety and VoIP tokens), configure outbound password-reset email, storage cleanup/backup retention, APNs credentials, Redis/Channels, TURN and push delivery. Check authenticated account recovery/deletion, reporting/blocking, uploads, organization ownership transfer and calls against the deployed backend using dedicated test accounts. Public JSON 401/405 responses establish route reachability only.

## Build-only procedure

From `mobile/`, authenticate with `npx.cmd eas login`, link the owner's existing project, set the real production EAS environment values described in `RELEASE_READINESS.md`, and configure existing remote Android/iOS signing credentials with `npx.cmd eas credentials`. Confirm app identifiers before registering them; do not silently create a new identity. Supply Firebase configuration via an EAS file variable. Public Expo environment variables are bundled into the app and must contain no secrets.

Run `npm.cmd run typecheck`, the relevant Node tests, `npm.cmd run check:release`, and `npm.cmd run check:urls`. The local preflight requires the same production values; it currently blocks missing configuration. Then run `npm.cmd run build:android` and `npm.cmd run build:ios`. Both freeze remote credentials. Record the resulting EAS build IDs and download URLs, verify signature/package/version and retain the upload key securely. Never add `--auto-submit`, run `eas submit`, or publish an EAS update as part of this task.

## Store compliance gates

- Verify the final AAB targets Android API 36 or higher and native libraries support 16 KB pages. Installed React Native source defaults target/compile SDK to 36; source inspection is not signed-artifact verification. See [Google target API requirements](https://developer.android.com/google/play/requirements/target-sdk).
- Verify the iOS build logs use Xcode 26 or later and iOS 26 SDK or later, required for uploads since April 28, 2026. EAS image selection and successful native build remain unverified. See [Apple requirements](https://developer.apple.com/news/upcoming-requirements/?id=02032026a).
- Complete Play Data Safety and App Store privacy disclosures using `DATA_INVENTORY.md` and actual backend/provider practices. Inspect merged privacy manifests and required-reason APIs from native dependencies; validate encryption/export-compliance answers before setting any exemption flag.
- Confirm in-app account deletion and the public external deletion flow. [Google requires a functional external pathway](https://support.google.com/googleplay/android-developer/answer/13327111?hl=en); [Apple requires deletion within the app](https://developer.apple.com/support/offering-account-deletion-in-your-app/).
- Provide moderation operations, published community/child-safety standards as applicable to the social category, reporting/blocking, a monitored safety contact and a handling/escalation process. Do not equate implemented report buttons with a staffed moderation service. Complete age/content ratings, target audience, ads and social-app declarations based on actual behavior. Web advertising exists: free launch alone is not evidence for a “contains no ads” answer.
- Inspect final Android merged permissions and complete foreground-service declarations for native calling. Validate PushKit/CallKit compliance on iOS and notification/Telecom behavior on Android, including locked/terminated devices and cancellation. Test calls across separate networks using TURN.
- Keep purchases unavailable at launch. Do not claim paid digital features or advertise purchase links until compliant billing is implemented.
- Supply real screenshots from the signed builds, including iPad because tablet support is enabled; final icon/artwork, category, release notes, territories, support contact and reviewer instructions. Supply dedicated talent and organization-owner review accounts through store review fields, never Git.
- Verify applicable developer identity, organization and regional trader disclosures in each console. New Google personal developer accounts may require [12 opted-in testers for 14 continuous days](https://support.google.com/googleplay/android-developer/answer/14151465?hl=en) before production access. That testing/upload is a separate action and was not performed here.
- Complete physical-device accessibility, permissions denied, offline/reconnect, cold start, keyboard, tablet, crash and performance checks. Resolve or explicitly assess dependency security findings before release.

Store forms remain drafts. No signed AAB/IPA, device acceptance evidence, reviewer credentials or store-console verification exists yet.

## Verification in this continuation

30 isolated backend tests and 13 targeted Node tests passed. TypeScript, Django checks, migration drift and Git whitespace checks passed. Live public backend checks returned the expected 200/401/405 statuses; all four policy/support/deletion pages returned 404. Both-platform EAS production build attempt stopped at missing Expo authentication, before build creation. Fresh online `npm audit --omit=dev` reports 19 high findings, zero critical/moderate/low; see [SECURITY_AUDIT.json](SECURITY_AUDIT.json). Suggested automated fixes include incompatible framework downgrades; no forced downgrade was applied. Dependency risk remains unresolved.

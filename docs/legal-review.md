# Awinlink policy draft review

Draft set: `2026-11-04-draft-2`, reviewed against the local implementation November 4, 2026. **Not approved for release.**

Previous exact policy template sources are archived in [legal-archive/2026-10-18-draft-1](legal-archive/2026-10-18-draft-1/README.md). This is not a historical rendered-page capture. Web/API and mobile registration now use the new draft version; existing acceptance records are unchanged. Coordinate backend/mobile release because older registration clients will correctly reject a stale version.

Review the rendered `/terms/`, `/privacy/` and `/community-guidelines/` pages and their source in `core/templates/core/policies/` with counsel and the service operator. Existing support and account-deletion routes remain available.

All five public legal/support/deletion pages retain a draft warning and a machine-readable draft marker. Supplying operator configuration does not approve them. The URL preflight now rejects reachable draft pages, including community standards. Do not remove either warning or marker without explicit operator/legal approval of the exact copy and a separately reviewed release change.

## Operator confirmation required

No values below were invented or inferred from a developer username, app ID or hosting account. Blank/invalid contacts remain visibly incomplete. The operator may explicitly confirm the same monitored mailbox for several functions.

| Required confirmation | Configuration or evidence needed |
| --- | --- |
| Legal operator and postal address | `AWINLINK_LEGAL_OPERATOR`, `AWINLINK_LEGAL_ADDRESS`; confirm listing/entity consistency |
| Monitored support, privacy and child-safety channels | `AWINLINK_SUPPORT_EMAIL`, `AWINLINK_PRIVACY_EMAIL`, `AWINLINK_CHILD_SAFETY_EMAIL`; verify ownership and monitoring; register the designated CSAM contact in Play Console where applicable |
| Countries, intended ages and legal eligibility | Launch territories, Play target audience/content rating, applicable local ages, processing grounds and parental-consent requirements; do not equate technical bands with legal eligibility |
| Guardian verification and requests | Staff reviewers, relationship/adult verification method, evidence minimization, case-reference handling, verified parent/child access/correction/deletion, appeals, reauthorization and adulthood handover. Review/minimize the child's registration data collected before guardian approval; account restriction alone does not establish a lawful basis for collecting it. |
| Retention/deletion | Approved maximum periods and reasons for account/guardian records, logs, temporary auth attempts, classroom records, ad events, reports, files/CDNs and backups; actual purge/restore evidence; no blanket legal exemption assumed |
| Providers and transfers | Active legal entities, service roles, regions, subprocessors/contracts and transfer safeguards for hosting, storage/CDN, mail, notifications, Google, TURN, payments and backups; SDK/analytics/advertising inventory from the final artifact |
| Moderation and incidents | Staffed report handling, known-CSAM removal/reporting/preservation process under applicable law, child-safety contact, incident response, notices and appeals; no invented response deadline |
| Commercial/legal terms | Content-license duration, pricing/refunds, warranties/liability, governing law/disputes, regional user rights/complaint routes and policy-change notices |
| Release signoff | Exact approved versions/rendered pages, owner/counsel approval, deployment verification and matching Play Data Safety/target-audience/SDK declarations |

## Verified implementation and remaining gaps

| Practice | Source evidence and disposition |
| --- | --- |
| Age and guardian information | `accounts/models.py`, `age_policy.py`, `guardian_permissions.py`: private DOB/source; nominated guardian email; review case reference/actors/times; consent/audit and contact/course grants. Registration details are stored before approval. Manual review is not a certification of legally sufficient parental consent. |
| Restricted access | `age_middleware.py`, authentication and shared policies: public legal/support information remains readable for restricted sessions; protected actions remain denied. Guardian progress access does not grant private messages/quiz answers or teaching roles. |
| Google identity/deletion | `google_auth.py`, `deletion.py`: subject-based linking, 10-minute login and 5-minute deletion challenge expiry; fresh signed authentication time for deletion; provider tokens not persisted. Expiry is not physical erasure. `clear_google_auth_attempts` exists; scheduler execution is unverified. |
| Sponsored content | `advertising/services.py`: profile targeting and impression/click/video-view events exist. This review restricts delivery, token issuance, feed insertion and tracking to currently active known adults, including denial of old tokens after age changes. Adult advertising remains. Do not declare “no ads” or SDK compliance without final-build/provider verification. |
| Calls, devices and storage | WebRTC direct/relay routing can expose network addresses; camera/mic/screen-share features and stored attachments exist. Native secure credentials, browser session storage/cookies, notification tokens and alert payloads need accurate disclosures. No stored-message E2EE assertion. |
| Automatic database deletion | Account, owned posts/messages and linked identity cascade; organization owners must transfer first. Shared classroom creator/inviter references use PROTECT: deletion now returns an actionable conflict and rolls back rather than a server error. A verified support resolution/erasure procedure is still needed; none is invented here. |
| Surviving personal data | Classroom chat/whiteboard/audits, ad events and reports can survive with a user link removed. Free text can remain identifying. Full erasure, lawful retention purposes and maximum periods need review; unlinking is not anonymization. |
| Media/backups | Some scoped cleanup exists, but universal physical erasure, historical public-CDN invalidation, offsite backup rotation/restore safeguards and production completion are unverified. Do not claim deletion removes all files immediately. |
| Providers | Code supports Cloudinary/filesystem, Railway/VPS, SMTP/Resend, Google OAuth, Expo/FCM/APNs/web push, TURN and Paystack web advertising payments. Code/configuration support is not evidence that a provider is active in production. |
| Child safety still open | In-app pre-sharing safety reminders, SDK/identifier review, legal age assurance, operational verification, manual support requests and production/device tests are not completed by policy prose. |

Google Play review references: [User Data](https://support.google.com/googleplay/android-developer/answer/10144311?hl=en), [Families](https://support.google.com/googleplay/android-developer/answer/9893335?hl=en), [Child Safety Standards](https://support.google.com/googleplay/android-developer/answer/14747720?hl=en). These require operational evidence as well as accurate published text; this review does not certify compliance.

The privacy draft describes local source behavior, not the effective deployment.
The confirmation table above is the release checklist. Do not replace unknown
operations with promises or imply that documenting a limitation closes it.

## Acceptance behavior

New Django and API registrations must submit `terms_accepted` affirmatively and the exact `terms_version`. Django supplies the current version in a hidden field; Expo sends its bundled version alongside the unchecked-by-default control. Missing or stale versions fail with a field error. Clients cannot choose the stored timestamp or acceptance version: the shared registration form stamps the server time and validated current version.

Migration `accounts.0006_user_terms_acceptance` adds an empty version and nullable timestamp to existing users. No acceptance is inferred, no login gate is added, and existing sessions remain valid. No IP address or user agent is collected for this record. Admin/management account creation is not a public registration flow and retains empty values unless separately handled.

When the draft is approved or the Terms text changes, archive the exact previous rendered Terms and corresponding source/version in version control, assign a new version in `accounts/legal.py` and `mobile/src/legal.ts`, and update the policy copy and date together. Never silently rewrite an accepted version. Plan renewed acceptance for existing users separately if required; this change does not invent it or automatically accept updated Terms. Do not release these draft policies until review is complete.

## Local verification for this review

- `scripts/check_age_accounts.py test accounts core.test_public_pages advertising`:
  266 tests, 262 passed and 4 skipped, on disposable SQLite/local services.
- Targeted mobile legal-readiness, Terms/registration and Google authentication/
  deletion suites: 22 passed. After deletion-disclosure wording was aligned,
  the 8 legal-readiness/deletion tests passed again.
- TypeScript, Django system checks, migration consistency, URL-check script
  syntax and Git whitespace checks passed. This review adds no schema migration.
- Previous policy template archives match their prior committed source bytes.
- No production database, external account, build, deployment, commit or push was
  changed. Live policy publication, final-artifact/SDK and provider verification,
  operational retention/deletion and owner/legal approval remain outstanding.

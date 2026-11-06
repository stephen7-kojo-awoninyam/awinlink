# Play Data Safety and privacy disclosure worksheet

Status: **draft; operator confirmation and Play Console review required**. This is
a source inventory, not a submitted declaration or certification. Policy draft:
`2026-11-04-draft-2`. See [legal review](../../docs/legal-review.md).

| Data observed in source | Purpose / recipients | Retention and release questions |
| --- | --- | --- |
| Username, name, email, user-supplied phone/country, role | Account access, profile, recovery, organization administration | Required versus optional fields; pre-approval child data minimization; maximum retention |
| Private birth date/source and derived age band | Age restrictions; signed-in account/authorized staff | Self-reported; unknown legacy ages remain unknown; not public profile data |
| Guardian nomination email, guardian/reviewer IDs, verification case reference/times | Manual authorization of adult guardian and relationship | Actual verification evidence, lawful consent method, limits on case-reference content and access |
| Guardian consent version/time, audit events, contact/call/course/live permissions | Scoped controls, revocation, progress access | Separate from Terms acceptance; deletion/withdrawal/adulthood handover procedures and retention |
| Google subject, verified email/name, temporary nonce/verifier/claims; signed auth_time for deletion | Optional Google OAuth and fresh deletion confirmation | Provider tokens not persisted by integration; 10/5-minute challenge deadlines are not purge deadlines; confirm cleanup scheduling |
| Password hashes, JWT/refresh sessions, browser sessions/CSRF and native secure credentials | Authentication/security | Token expiry/revocation, device storage/backup rules, logs; do not describe hashed credentials as plaintext |
| Terms version and server acceptance time | Registration acceptance record | Historical versions unchanged; no inferred acceptance, marketing consent or automatic renewed acceptance |
| Profiles, posts, comments, likes, portfolios, media, follows/saved items | User publication and collaboration; authorized recipients | Known-minor discovery/structured data protections; free text/EXIF and historical public URLs remain risks |
| Messages, files, images, videos and voice messages | Conversations and authorized recipients | Sender cascades do not prove file erasure; stored messages are not E2EE |
| Call/classroom IDs, participants, attendance, status/timing, signaling and network data | WebRTC participants and configured TURN operators | Direct peer network-address exposure; review actual capture/recording behavior and logs; no blanket relay-only claim |
| Course content, quiz attempts/answers, progress, certificates, classroom chat/whiteboard and audits | Authorized learners/staff; guardian-scoped progress | Guardians do not gain private answers/messages; shared text/audits can survive author unlinking; PROTECT references need support resolution |
| Applications, recruitment, team membership, invitations, offers/deal messages | Authorized participants/organization roles | Exact surviving records, access controls, business/legal retention and erasure procedures |
| Push/VoIP tokens, browser subscriptions/keys, device platform, alert content/routing | Expo, FCM, APNs, browser push where configured | Provider data flows/regions, lock-screen previews, token cleanup and retention |
| Interests, recommendations, impressions/dismissals and first-party analytics | Discovery/ranking; recipients depend on feature | Enabled flags/profiling and actual SDK/analytics inventory; do not assume all analytics are third-party or absent |
| Web sponsored campaigns, targeting categories/domains/skills/sports, impression/click/video events and tracking hashes | Ad selection/frequency/metrics | Delivery, token issuance and tracking now exclude minors/unknown-age users. Adult ad events may survive with user relation removed; confirm recipients/retention. Do not declare “no ads” solely from free pricing |
| Advertising payment email, amount/currency/reference and web payment status | Paystack if web advertising payments enabled | Confirm launch configuration and processor contracts; native billing is not established by this feature |
| Blocks, reports, optional public-report reply email and moderator review notes/actor/time/history | Moderation/security/support; authorized reviewers only | Public intake works without login or email and accepts no attachments. Reports can survive with reporter relation removed; text/email may remain identifying; approved reasons and maximum periods are pending. Review status does not prove external legal reporting or media erasure |
| Technical logs, request/network metadata and hashed abuse-limit keys | Hosting, cache/security and mail services | Actual logged fields, third-party access, periods, incident processes and cross-border arrangements |

Supported integrations are not a verified production vendor list. Source supports
Railway/VPS hosting, Cloudinary/filesystem media, PostgreSQL/SQLite and Redis/cache,
SMTP/Resend mail, Google OAuth, Expo/FCM/APNs/web push, TURN and Paystack web ad
payments. Confirm active legal entities, regions, subprocessors, contracts,
backup operators and any SDK behavior in the **exact signed artifact**.

Before answering Play forms, assess each data category's collection, sharing,
purpose, optionality, deletion and security using actual behavior and Google's
definitions/exemptions. Do not assume user-initiated sharing or service-provider
exceptions, declare no sale/sharing, or infer SDK child suitability without review.
Camera/mic/file permissions and network-derived location need final-artifact review.

Account deletion is available inside the app and at `/delete-account/` without
reinstalling. Password accounts retain password confirmation; linked Google
accounts can use a fresh, purpose-bound Google challenge. Guardian restrictions
and organization ownership rules remain. Shared learning references may block
automatic deletion with an actionable conflict. Surviving shared records,
uploaded files, historical CDN URLs and backups need approved erasure/retention
handling. Unlinking a user does not anonymize free text.

Public policies/support/deletion/community pages **remain drafts**. Contacts and
postal address are configurable but unconfirmed until the operator supplies and
verifies them. The URL preflight rejects drafts even when HTTP 200 and contacts
are filled in. No policy approval, legal compliance, console submission, exact
artifact inclusion, production migration, deployment or physical erasure is
established by this worksheet.

Review references: [User Data](https://support.google.com/googleplay/android-developer/answer/10144311?hl=en),
[Families](https://support.google.com/googleplay/android-developer/answer/9893335?hl=en),
[Child Safety Standards](https://support.google.com/googleplay/android-developer/answer/14747720?hl=en).

# Public Child Safety Standards page

The local Django route `/child-safety/` (`child_safety`) renders the shared public
legal template and a dedicated standards page. It is linked from public legal
navigation, uses blue/white styling with a single-column mobile breakpoint, and
requires no login, JavaScript or remote font/asset service. Restricted minor
sessions may read GET/HEAD without gaining access to protected account actions.
The standards page's non-deletion POST behavior remains intact. A separate
`/child-safety/report/` contact form now accepts CSRF-protected, rate-limited,
text-only submissions without granting account access.

The page retains the draft warning and the existing policy-set version. Its
review date is November 5, 2026; existing Terms text and acceptance versions are
unchanged. Contact links use the existing validated `AWINLINK_CHILD_SAFETY_EMAIL`
and `AWINLINK_SUPPORT_EMAIL` settings; missing contacts are explicitly flagged.
Configuration alone does not approve the page or verify monitoring. The working
database-backed form is an independent contact path when no mailbox is configured;
it does not prove that staff are monitoring reports or that a named Play Console
point of contact exists. No test email or external legal report was sent.

A sanitized local configuration check on November 5 found operator identity,
postal address, support email, privacy email and child-safety email missing or
invalid. This was not a production environment or mailbox-delivery verification.
The operator has been asked to confirm the mailbox, named owner and operating
entity/countries; no values were invented or silently configured.

Subsequent operator instruction supplied **stephenkojoawoninyam@gmail.com** as the
designated child-safety email. `AWINLINK_CHILD_SAFETY_EMAIL` is now set in local
`.env` and the VPS environment example; public templates explicitly say monitoring
and email delivery have not been verified. This supersedes only the earlier local
child-safety-address gap, not the missing legal/operator details, staffing, mailbox
verification or production/Console configuration. No email was sent and sender,
support/privacy, credentials and other environment settings were not repurposed.

The [operational readiness checklist](child-safety-readiness-checklist.md) records
technical blockers separately from operator responsibilities and legal decisions.

## Evidence behind the copy

- `accounts/mobile_api.py`, `mobile/app/report.tsx`: signed-in user/post/message
  reports retain access checks and existing categories; `child_safety` is explicit.
  General incidents use target type `safety`, ID 0, a minimum description and no
  private target lookup. Account and safety links to this in-app path.
- `core/safety_views.py`: anonymous/public text intake with optional reply email,
  bounded fields, CSRF, shared-cache rate limits, attachment rejection and no
  false receipt on cache/database failure. Restricted users can submit to this
  standalone form while protected API/account actions remain denied.
- `accounts/models.py`, `accounts/admin.py`, `report_review.py`: prioritized
  child-safety queue and permission-checked review/escalation/resolution/reopening,
  required notes and read-only admin review history. Direct status editing and
  casual admin deletion are disabled. Post removal requires `feed.delete_post`,
  is atomic with the audit event, and leaves the case requiring escalation for
  media/evidence/legal work. Other content/author accounts are not automatically
  removed or suspended. A status does not prove that an external action happened.
- `accounts/safety.py`, `age_policy.py`, `guardian_permissions.py`: blocking,
  current age/guardian checks and scoped permissions; no automatic identity
  assurance or unrestricted guardian access is asserted.
- Existing privacy/community drafts document enforcement possibilities, surviving
  records, missing operations, historical public media and manual support work.

The page prohibits CSAE/CSAM and gives reporting instructions while distinguishing
implemented controls from missing staff/processes. No automated detection,
24/7 monitoring, guaranteed response/removal deadline or external authority
reporting integration is invented. It does not ask users to redistribute CSAM.

## Google Play requirement assessment

These statuses concern local implementation unless stated otherwise. Applicability
depends on the app's actual category/behavior; see Google's linked policy. There
is **no overall compliance claim** and draft warnings remain.

| Child Safety Standards requirement | Verified locally | Remaining review / release evidence |
| --- | --- | --- |
| Published anti-CSAE/CSAM standards | PASS: anonymous HTTP 200 HTML, Awinlink branding, explicit rules and reporting links | PENDING: approval and production publication of the exact new standards; live pages inspected previously were older drafts |
| In-app feedback/reporting | PASS: target-checked reports, explicit child-safety category and general incident route; public fallback intake | PENDING: final signed-build/device and deployed-backend acceptance; staff monitoring. No broader private-record access is granted |
| Address known CSAM | PARTIAL: authorized database post removal, review notes/history and escalation tracking | PENDING: actual trained/staffed handling, message/media cases, public CDN copies, evidence controls, notices/appeals and proof of completed takedown. Automatic scanning is not mandated by Google |
| Comply with applicable child-safety laws/reporting | PENDING: system can record review/escalation notes and case references, not legal completion | Operator entity/countries, qualified legal review, authority/channel, triggering conditions, applicable deadlines, evidence/preservation rules, authorized sender and actual report receipts must be established. No jurisdiction inferred and no report automatically sent |
| Child-safety point of contact | PARTIAL: usable public intake, admin queue and locally configured designated email `stephenkojoawoninyam@gmail.com` | PENDING: confirmed named owner, mailbox control/monitoring/delivery, staffing and production/Play Console designation. A form or syntactically valid address does not verify these |

Related Families work is separate: pre-sharing safety reminders across freeform
content, intended-age declarations, SDK/identifier review, consent/age assurance
and privacy/retention remain open. Warnings on the report screen are not presented
as the complete Families pre-sharing implementation.

## Data and rollout

Migration `accounts.0011_child_safety_reporting` adds optional contact email, new
choices and review-event storage. Existing reports keep their status/details and
have no fabricated historical reviews. This migration has only been exercised in
disposable tests; a separately authorized migration/backend/mobile rollout is
required before the new features work on production. Do not deploy the mobile
general-report client before its backend support.

Public report text and optional reply email, plus staff review notes, are personal
data visible only to authorized reviewers. Avoid graphic content/identity documents;
no evidence attachment or URL fetching is implemented. Retention, access requests,
lawful handling of reports from children, storage erasure and reviewer training
still require approval. Admin read-only history is not a claim of tamper-proof
database storage. Privileged retention/erasure procedures remain to be designed.

See [operator runbook and unconfirmed legal fields](child-safety-operations.md).

## Remaining release requirements

Confirm monitored contacts and operator/legal approval; designate the appropriate
Play Console child-safety contact; implement/verify staffed triage, known-CSAM
handling/removal, lawful evidence/escalation, notices and appeals. Complete the
applicable Families pre-sharing reminder, SDK/identifier and age/guardian review,
retention/media protection and final-build/production verification. Automated
CSAM scanning is not represented as a Google-mandated implementation method.

The read-only URL preflight now includes this route and rejects draft pages.
This code change does not publish a live URL or complete a Console declaration.
See [legal review](legal-review.md) and [Google's requirements](https://support.google.com/googleplay/android-developer/answer/14747720?hl=en).

## Published policy inspection

Anonymous read-only HTTPS checks on November 5, 2026 returned HTTP 200 for the
Railway production `/privacy/`, `/terms/`, `/community-guidelines/` and `/support/`
pages. Those published policy pages still displayed `2026-10-18-draft-1`, and
support stated that no public support email was configured. They do not establish
deployment of the newer local policies or safeguards. No production settings,
records, policy pages or application code were changed during those checks.

## Initial page verification (before the intake/review extension)

- Child-safety/public-page, age-account and mobile API regression suites: 46
  passed using disposable SQLite/local test services. Coverage includes anonymous
  HTTP 200 HTML, HEAD, rejected POST, restricted minor read access, draft/contact
  handling, reporting limitations and responsive markup/navigation.
- Legal-preflight tests: 2 passed. URL-check JavaScript syntax, Django system
  checks and scoped Git whitespace checks passed.
- Responsive CSS and viewport markup are covered; no physical-device or browser
  layout acceptance, production enforcement, build, deployment or Console
  certification is claimed. No commit, push or production migration was run.

## Intake/review regression validation

- Focused reporting, public-page and legacy mobile API suite: 37 passed.
- Broader account/public-page regression suite: 267 run, 263 passed / 4 skipped.
- Final intake/review/security suite: 12 passed, including admin queue access,
  CSRF, read-only generic admin status, escaped review history, permission denial,
  audit rollback, text-only contact, no false receipts and restricted-account limits.
- Focused mobile reporting, deletion and legal-readiness tests: 13 passed; after
  final wording alignment the 7 reporting/readiness tests passed again.
- TypeScript, Django checks, migration drift and Git whitespace checks passed.
- All backend writes/migrations were on disposable local test databases. Mailbox
  delivery, actual staff response, legal reporting, PostgreSQL/Redis production
  behavior, final signed artifact, deployment and Console declarations were not
  verified or performed. Draft warnings remain; no compliance claim is made.

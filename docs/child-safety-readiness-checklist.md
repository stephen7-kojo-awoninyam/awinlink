# Google Play child-safety operational readiness checklist

Reviewed November 5, 2026. **NOT READY / no compliance claim.** Local implementation
and configuration are not production, staffing or legal verification. Draft
warnings remain. No deployment, commit, push or production migration is authorized
by this checklist.

## Designated contact and configuration scope

- Designated email supplied by the operator: **stephenkojoawoninyam@gmail.com**.
- Configured as `AWINLINK_CHILD_SAFETY_EMAIL` in ignored local `.env` and in the
  VPS environment example for a future, separately approved rollout.
- Public child-safety, reporting, community and support pages display the address
  with an explicit monitoring/delivery-unverified notice when that setting is used.
- **Unverified:** mailbox ownership/control, inbound/outbound delivery, spam-folder
  handling, monitoring, response coverage, named primary/deputy and Console entry.
- This does not configure production, a mail sender, SMTP credentials, Resend,
  forwarding, support/privacy contacts or automated notifications. No email sent.
- Public `/child-safety/report/` intake stores reports independently of email;
  intake persistence does not establish that a person responds.

## Requirement map

| Google Play Child Safety Standards requirement | Local evidence | Release status |
| --- | --- | --- |
| Published anti-CSAE/CSAM standards | Anonymous HTML page, rules, reporting links, draft disclosure | PENDING approval and public production verification |
| In-app feedback mechanism | Item reports, explicit child-safety reason and general incidents; public fallback | Locally tested; PENDING exact-build/device/backend verification and staff operation |
| Appropriate action on known CSAM | Audited staff review and permission-checked database post removal | PARTIAL: complete message/media/CDN handling and actual response evidence missing |
| Compliance with applicable child-safety laws | Escalation notes can record limited references | PENDING jurisdiction-specific legal procedure and actual required reports |
| Designated child-safety point of contact | Supplied address configured locally; working intake | PENDING named responsible individual, verified mailbox/monitoring and Console designation |

Source: [Google Play Child Safety Standards](https://support.google.com/googleplay/android-developer/answer/14747720?hl=en).
The policy does not prescribe a particular automated detection method. A scanner
or automatic authority-reporting integration is not substituted for actual handling.

Every unchecked item below remains unresolved. Role names are proposed
responsibilities, **not appointments**. Assign a real person, due date, evidence
reference and reviewer before marking an item complete.

## Technical blockers — engineering / infrastructure

| ID | Required check and completion evidence | Dependency |
| --- | --- | --- |
| T1 | [ ] Rehearse then separately authorize migrations/backend rollout, including `accounts.0011_child_safety_reporting`; verify schema, backup/restore and existing-report preservation | Rollout approval; no production migration performed here |
| T2 | [ ] Verify the signed mobile artifact contains child-safety entry/category/general incidents and matches the deployed API; test old categories, denied private targets, retry/offline and restricted-account fallback | Backend before new client; exact artifact provenance |
| T3 | [ ] Verify public `/child-safety/` and `/child-safety/report/`, contact links, HTTPS, anonymous/mobile access, CSRF, rejected attachments and failed-storage behavior on production | Approved copy and deployment |
| T4 | [ ] Verify shared-cache throttling across workers, access permissions, case history and audit rollback on the production PostgreSQL/Redis stack | Infrastructure evidence; local SQLite tests are insufficient |
| T5 | [ ] Implement/verify removal or access restriction for affected messages, files and other media beyond database posts; prevent continued retrieval through every app/media endpoint | O3 and approved evidence/preservation decisions |
| T6 | [ ] Inventory private/original/public storage URLs, thumbnails/transforms and historical CDN copies; verify denial/invalidation at warm CDN edges with benign fixtures and an independent client | Storage operator access; L2/L3. Database deletion alone does not pass |
| T7 | [ ] Verify the approved procedure for backup/replica copies, preservation exceptions, expiration and safe restore without republishing removed content | Approved legal retention/preservation rules |
| T8 | [ ] Implement/verify the chosen monitoring/notification mechanism and operational access controls | O1/O2 define coverage; automatic email is optional if the approved queue-monitoring process is effective |
| T9 | [ ] Implement/verify notices and appeal intake/tracking to support the approved operator/legal process | O4 and L4 |
| T10 | [ ] Complete applicable Families pre-sharing reminders, SDK/identifier, intended-age and guardian/privacy checks | Separate Families review where applicable; report-screen warnings do not complete it |

Use benign test material. Do not upload, circulate or copy CSAM to demonstrate
removal. Record actual request outcomes and case references, not illegal evidence
in ordinary reports, email, chat, screenshots or source control.

## Operator decisions — safety lead / service owner

| ID | Responsibility to assign and evidence needed | Current state |
| --- | --- | --- |
| O1 | [ ] Name a primary safety lead and deputy; confirm authority, competence, access and handover; designate the appropriate individual/address in Play Console | No person or Console entry verified; do not infer a name from the email |
| O2 | [ ] Confirm mailbox control and monitoring; approve benign delivery tests separately, record receipt/reply timestamps, check spam handling, set coverage hours and urgent/out-of-hours escalation | Address designated only; no test sent, no monitoring/24-hour coverage or deadline claimed |
| O3 | [ ] Assign trained triage/review staff, a media-removal owner, evidence custodian and incident coordinator; approve suspected/known-CSAM decision criteria and urgent-risk handling | Queue exists, staffing and end-to-end handling unverified |
| O4 | [ ] Assign notice/appeal handlers and an independent review/escalation path where appropriate; approve channels, response targets, exceptions, outcomes and records | Support requests/reopening are not a complete appeals procedure |
| O5 | [ ] Assign an authorized external-reporting person and qualified legal contact; train staff on approved authority/evidence channels | Not assigned or verified; ESCALATED sends nothing externally |
| O6 | [ ] Approve least-privilege reviewer access (`accounts.change_contentreport`), separate post-removal permission (`feed.delete_post`) and access review/offboarding | Permissions exist; actual assignments/coverage need review |
| O7 | [ ] Approve closure criteria: actual restriction/removal, storage/CDN results, lawful preservation, any required authority receipt, notices/appeal handling and outstanding exceptions | RESOLVED alone is not proof of completion |
| O8 | [ ] Approve exact public copy, contact disclosures, operational promises and matching Play declarations | Drafts retained; no approval or compliance certification supplied |

## Legal decisions — confirmed operator and qualified reviewer

| ID | Decision required before an approved legal reporting procedure exists |
| --- | --- |
| L1 | [ ] Confirm legal entity, establishment, service territories and applicable jurisdiction(s); determine the app's actual category/behavior and policy applicability. Do not infer these from Gmail, hosting, time zone or user profile countries |
| L2 | [ ] Determine reporting triggers, appropriate authority/channel, any statutory deadlines, authorized sender and required receipt/case-reference records for each applicable jurisdiction. No universal authority or deadline is assumed |
| L3 | [ ] Approve lawful evidence access, preservation, minimization, custody/transfer, retention/deletion and backup/CDN exceptions. Ordinary report tables and this Gmail address are not an approved CSAM evidence repository |
| L4 | [ ] Approve confidentiality, user/guardian notices, disclosure restrictions, appeal rights/processes and lawful exceptions without compromising safety/investigations |
| L5 | [ ] Review age/guardian assurance and data collection before approval, anonymous child reports/optional reply email, access/deletion requests, processor/transfer arrangements and retention purposes/periods |

The existing system records escalation and limited references; it neither decides
which law applies nor submits reports to an authority. A documented legal procedure
must be approved and exercised by authorized personnel where required. Do not
mark L2 complete from an admin status change or a generic email confirmation.

## Evidence and signoff record

For each item record: `ID | named owner | decision/date | implementation/evidence
reference | verifier/date | outstanding exceptions`. Keep sensitive evidence in
an approved system; reference it without placing it in this repository.

- [ ] Technical lead verifies deployment/build/media and access-control evidence.
- [ ] Safety lead confirms staffing, monitoring, removal and appeal operations.
- [ ] Qualified legal reviewer approves applicable reporting/preservation duties.
- [ ] Operator approves the exact standards, privacy/retention disclosures and
  Console declarations against that evidence.
- [ ] Review every remaining item/exception before a release decision; remove
  draft warnings only through a separately approved change after issues resolve.

No compliance claim or automatic signoff is created by completing this document.
See [operations](child-safety-operations.md), [standards assessment](child-safety-standards.md)
and [legal review](legal-review.md).

## Verification of this checklist/configuration change

- Local Django settings read-back matched the supplied designated address; `.env`
  is Git-ignored. Other mail/contact settings were not repurposed.
- 32 focused public-page and intake/review regression tests passed on disposable
  local test services, including contact visibility and unverified-status/draft
  warnings on standards, report, support and community pages.
- Scoped Git whitespace checks passed. No new schema migration was created.
- No email/delivery test, mailbox access, staff appointment, Console update,
  production configuration change, deployment, commit, push or production
  migration was performed. Existing historical test evidence is not replaced with
  claims of operational or legal verification.

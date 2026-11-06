# Child-safety operations: technical runbook and approval gates

Status: **operator/legal review required; not a completed legal reporting SOP**.

Use the [operational readiness checklist](child-safety-readiness-checklist.md) to
separate technical blockers (T), operator assignments (O) and legal decisions (L).
The operator-designated address is **stephenkojoawoninyam@gmail.com**, configured
locally as `AWINLINK_CHILD_SAFETY_EMAIL` and in the VPS environment example only.
Ownership, delivery, monitoring, primary/deputy and Console designation are not
verified. No email was sent; no production configuration changed.

## Implemented handling

1. Reports arrive through existing item Report controls, Account and safety →
   Report a child-safety concern, or `/child-safety/report/` without login.
   Text only; no CSAM attachments, private-target fetching or outgoing email.
2. Authorized staff use the Content reports admin queue. Open child-safety reports
   sort ahead of ordinary reports. A named owner/monitoring schedule is still needed.
3. Review / escalate requires an active staff account with
   `accounts.change_contentreport`. Required notes record an actual decision or
   internal case reference. OPEN can become REVIEWED or ESCALATED; resolution
   requires review/escalation first; resolved reports can be reopened.
4. The optional Remove reported post action also requires `feed.delete_post` and
   the ESCALATED destination. Database post deletion and review history commit
   together. It does not guarantee storage/CDN erasure, suspend the author, remove
   unrelated messages or send a report to an authority. Investigate the allegation;
   user submission alone never triggers punishment.
5. History records actor/time/action/status/notes and is read-only in admin. Do not
   place illegal imagery, identity documents or unnecessary personal data in notes.
   Escalation status and closure notes are not evidence of legal compliance.

## Must be filled and approved by the operator / qualified legal reviewer

| Decision | Current state |
| --- | --- |
| Legal operator, establishment, service countries and applicable jurisdiction(s) | Unconfirmed; do not infer from usernames, hosting or user profile countries |
| Named safety owner/deputy, monitored mailbox and coverage schedule | Address designated as `stephenkojoawoninyam@gmail.com` and configured locally; named staff, ownership, delivery and coverage remain unverified |
| Play Console child-safety point of contact and declarations | Unverified; requires authorized Console review |
| Criteria for suspected/known CSAM and urgent-risk triage | Needs approved procedures and trained reviewers; do not equate a user report with a substantiated finding |
| Appropriate authority/channel, triggering duties and any deadlines | Requires jurisdiction-specific legal determination; no universal deadline or authority is invented |
| Evidence access, minimization, preservation, transfer and custody | Requires approved lawful procedures; do not ask users/staff to forward CSAM through ordinary reports/email |
| Known-CSAM restriction/removal beyond database posts | Needs verified message/media handling and historical public CDN cleanup, with actual completion evidence |
| Authorized external reporting person and report receipt/case-reference process | Unconfirmed; no automated external report has been implemented or sent |
| User notices, confidentiality, appeals and lawful exceptions | Requires approved procedures and implementation/verification |
| Retention/erasure, access requests, child-report data and audit access | Unconfirmed schedules/purposes; disabling casual admin deletion does not supply a lawful retention policy |

Once legal/operational decisions are approved, record actual actions and limited
references in the review history. Keep sensitive evidence only in an approved
system/channel; these report tables are not a CSAM evidence repository. Do not
close a case merely because a status changed. Verify storage and any required
external reporting independently, and document outstanding work accurately.

## Contact verification

The public form is functionally tested with no email configured: successful
submissions persist in the admin queue and failed storage does not show a receipt.
This establishes intake only. It cannot verify mailbox ownership, deliverability,
staff availability or law-enforcement procedures. No external messages are sent by
the tests or this change. Obtain those confirmations before removing warnings or
claiming compliance. Never substitute a fabricated mailbox or authority contact.

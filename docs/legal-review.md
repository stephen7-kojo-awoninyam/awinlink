# Awinlink policy draft review

Draft set: `2026-10-18-draft-1`, prepared October 18, 2026. Not approved for release.

Review the rendered `/terms/`, `/privacy/` and `/community-guidelines/` pages and their source in `core/templates/core/policies/` with counsel and the service operator. Existing support and account-deletion routes remain available.

Confirm before release:

- Legal operator identity, address, support/privacy contacts and applicable jurisdictions.
- Minimum age, minors' access, parental authorization and child-safety handling.
- Actual data inventory, all vendors, advertising/analytics, cookies, processing grounds, international transfers and user rights/request procedures.
- Database, upload, moderation-record and backup retention/deletion schedules.
- Content license, paid features/refunds, warranties, liability, governing law and dispute resolution.
- Moderation notices, appeals, emergency escalation and policy-change notification procedures.

The privacy draft describes implementation observed in this repository and leaves unverified operational commitments open for review. It does not certify compliance. Review reference: [FTC consumer privacy guidance](https://www.ftc.gov/business-guidance/privacy-security/consumer-privacy), including the need to honor published privacy commitments.

## Acceptance behavior

New Django and API registrations must submit `terms_accepted` affirmatively and the exact `terms_version`. Django supplies the current version in a hidden field; Expo sends its reviewed version alongside the unchecked-by-default control. Missing or stale versions fail with a field error. Clients cannot choose the stored timestamp or acceptance version: the shared registration form stamps the server time and validated current version.

Migration `accounts.0006_user_terms_acceptance` adds an empty version and nullable timestamp to existing users. No acceptance is inferred, no login gate is added, and existing sessions remain valid. No IP address or user agent is collected for this record. Admin/management account creation is not a public registration flow and retains empty values unless separately handled.

When the draft is approved or the Terms text changes, archive the exact previous rendered Terms and corresponding source/version in version control, assign a new version in `accounts/legal.py` and `mobile/src/legal.ts`, and update the policy copy and date together. Never silently rewrite an accepted version. Plan renewed acceptance for existing users separately if required; this change does not invent it or automatically accept updated Terms. Do not release these draft policies until review is complete.

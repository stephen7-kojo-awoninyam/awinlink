# Phase 2: roster-linked agreements

Transfers, sponsorships, ambassador deals, and contracts are private consent
records linked to an existing claimed, confirmed roster affiliation. They do not
create accounts, collect money, issue electronic signatures, infer historical
consent, or automatically publish commercial endorsements.

## Parties and permissions

Organization owners and managers receive `MANAGE_AGREEMENTS`. Recruiters retain
their existing roster/recruitment permissions but cannot create, approve or read
private agreements unless they are independently the linked talent. Viewers and
platform admin flags confer no agreement access. Existing membership suspension,
removal, active-account and active-organization rules remain authoritative.

For a commercial agreement, the organization submits and consents as **ORIGIN**;
the linked talent separately consents as **TALENT**. For a transfer, the current
roster organization submits as ORIGIN and both the talent and destination
organization must consent. A destination owner/manager acts as **DESTINATION**.
An account with more than one capacity must act explicitly for each party; one
button never signs on behalf of multiple parties.

Unclaimed, pending, declined or removed affiliations cannot start an agreement.
The talent must first confirm the roster link. Bilateral blocks with the acting
manager or linked organization account prevent new agreements/activation.

## Consent and lifecycle

1. Save a **DRAFT** with type, title, exact terms, optional dates/value/currency,
   and (for transfers) the destination organization, tag and roster. Saving does
   not give consent. Draft terms are private to current source owners/managers.
2. **SUBMIT** requires `consent: true` and the displayed `expected_revision`.
   This records the origin's actor, username snapshot, timestamp, revision and
   SHA-256 terms digest, and moves to **PENDING**. Counterparties can now read it.
3. **ACCEPT** requires separate explicit consent by each other party to the same
   revision. Commercial agreements become **ACTIVE** only after both parties
   agree. Transfers become **COMPLETED** only after all three parties agree.
4. Before activation, the service rechecks the source affiliation, active parties,
   blocks and each prior approver's current authority. Revoked or stale approval
   cannot activate an agreement. A current source manager can revise to collect
   fresh consent. Decline/withdraw closes a pending proposal with a required reason.
5. A source owner/manager may revise DRAFT/PENDING terms, incrementing the revision
   and returning to DRAFT. Old consents/events remain, but cannot count for the new
   revision. Parties, type and source affiliation are immutable; changing them
   requires a new proposal. Active/completed/closed terms cannot be edited.
6. Active commercial agreements can request **mutual ending**, recording consent
   and a reason in a new ending round. They remain **ENDING** until both parties
   explicitly consent to that round. Acceptance produces **ENDED**; the other
   party can decline the request and return the agreement to ACTIVE. A later
   request uses a new round so old ending consent cannot be replayed.

Dates describe the agreed period; they do not automatically activate, end or move
anything. Amount/currency record an agreed value only, with no collection, FX,
checkout, transfer fee or accounting operation.

Counterparties can retain access to previously submitted terms and consent
history when a source manager prepares a new private revision. The API presents
the last submitted version as read-only **SUPERSEDED**; it never returns the new
draft text or its private withdrawal reasons. History is filtered to submitted
revisions for counterparties. Drafts that have never been submitted, including
withdrawn drafts, remain private. SUPERSEDED is a read-only presentation state,
not a persisted lifecycle state.

## Transfer integrity and history

Transactions lock participating organization rows in ascending ID order, then the
agreement and source roster entry. Final consent, source removal, destination
creation, both roster history events, and the agreement decision commit together.
A conflicting destination entry rolls back the entire final decision, including
the new consent. A partial unique constraint permits at most one pending transfer
for a source affiliation. Repeated consent and approval-versus-revision races are
serialized and covered by PostgreSQL tests.

Only the named source affiliation moves. Other roster tags, staff memberships,
accounts, and existing commercial agreements are unchanged. Old agreements stay
with their original organization, talent and historical roster reference; they
are not assigned to the destination. A completed transfer cannot be "ended" to
reverse it. Any subsequent transfer starts a new three-party agreement.

Agreement events retain actor names, reasons, revisions and full terms snapshots
for creation/revision. Consents retain purpose, ending round, revision and digest.
Events and consent rows have no update/delete API. Protected foreign keys retain
agreement/roster history; removal in existing roster UI still changes status
rather than deleting records. Existing history remains readable to the talent
even after staff access is revoked.

## Web and mobile

Web: organization dashboard or Talent rosters → **Transfers, sponsorships and
contracts** (`/organizations/agreements/`). Each roster card links to agreements
filtered to its affiliation. The workspace supports all four draft types,
revision editing, explicit consent checkboxes, party-specific decisions, mutual
ending, and history including previously submitted exact terms. Text is escaped;
forms use local responsive styles and work at a 390px viewport.

Mobile: Profile → **Transfers, sponsorships and contracts**, or a roster card →
**View roster agreements**. The protected `/organization-agreements` screen uses
the authenticated API client, source/destination search, explicit consent
switches, revision-aware actions, historical terms, and ending-round checks.
Switching affiliations clears the draft, and the chosen affiliation remains
visible while searching. Client errors refresh permissions and agreement state.

## API

All paths below are relative to `/api/organizations/`. Authentication is required;
session writes enforce CSRF. Private responses use `Cache-Control: private,
no-store`. Lists/history paginate at 50; web/mobile follow pagination.

| Path | Operations |
| --- | --- |
| `agreements/` | GET accessible agreements, optional `?entry=<roster id>`; POST draft |
| `agreements/roster-choices/` | GET confirmed affiliations the caller can manage agreements for |
| `agreements/destinations/` | GET active organization names/IDs for transfer selection |
| `agreements/<id>/` | GET details/actions/consents; PATCH editable terms plus expected_revision; POST decision |
| `agreements/<id>/history/` | GET private, revision-filtered event history |

Draft input: `roster_entry_id`, `kind`, `title`, `terms`, optional `starts_on`,
`ends_on`, `amount`, `currency` (three uppercase letters, default GHS). Transfers
also require `destination_id`, `destination_tag` and optional destination_roster.
Commercial agreements cannot specify a destination. Values must be finite,
non-negative decimals, and end dates cannot precede start dates.

Decision input: `action`, `party`, `expected_revision`, explicit `consent` for
SUBMIT/ACCEPT/REQUEST_END/ACCEPT_END, and `reason` for
DECLINE/WITHDRAW/REQUEST_END/DECLINE_END. Ending actions additionally require the
displayed `expected_end_round`. Stale/conflicting decisions return 409. Unrelated
users see 404 for private agreement/history IDs. Clients use server-provided
actions for presentation; services always reauthorize within the transaction.

## Migration and validation

The follow-up [agreement security audit](../docs/agreement-security-audit-2026-10-21.md)
records consent validation, private lookup scoping, account safety locks, digest
integrity checks, concurrency regressions, and rollback verification.

`0013_roster_agreements` adds three tables and integrity constraints. It does not
update existing rows, infer agreements, backfill consent, or change roster
history. The migration is prepared only; application/production databases were
not migrated. Apply through the normal release process before serving the new
code. Retain schema/history instead of reversing this migration after records
exist; use a compatible forward change for rollback.

Tests: `organizations.test_agreements`, `organizations.test_agreement_postgresql`,
and `organizations.test_agreement_e2e`. The latter drives actual Chrome controls
and the mobile TypeScript agreement client against live JWT/session HTTP on an
isolated PostgreSQL test database. Set `AGREEMENT_TEST_CHROME` for browser coverage
and an explicit loopback `AWINLINK_AUDIT_POSTGRES_URL` naming `awinlink_audit_...`,
then run through `scripts/vc_audit.py`. Mobile screen regressions are in
`mobile/tests/organization-agreements*.test.cjs`. Physical Android/iOS device
rendering and electronic-signature providers are outside this implementation.

### Local verification, 2026-10-21

- Focused SQLite agreement tests: 17 passed.
- Consolidated PostgreSQL agreements, migration/concurrency and real HTTP/browser
  workflows: 23 passed. Final privacy/history changes were additionally rerun
  against PostgreSQL: all 17 agreement tests passed.
- Broader SQLite organizations/talents/invitations: 230 passed, 11 PostgreSQL-only
  tests skipped (241 total). The new owner/manager capability was added to the
  existing permission-matrix expectation; its 16-test suite passed separately.
- Full mobile suite: 113 passed, 3 unrelated browser-dependent tests skipped
  (116 total). New regressions cover consent controls, acting party, expected
  revision, ending rounds, drafts without automatic submission, revised terms,
  history and web text escaping. Mobile TypeScript passed.
- Django system checks, migration consistency, `git diff --check` and
  `git diff --cached --check` passed.

Chrome used real DOM forms and session/CSRF authentication for all four kinds,
private drafts, revised terms, mutual ending, three-party transfer, history and a
390px viewport. The actual mobile TypeScript agreement client used real JWT HTTP;
native screen controls were exercised by the mobile regression harness. These
checks do not substitute for physical Android/iOS rendering tests. A synthetic
browser capture is retained locally at `.audit-agreement-e2e/mobile-width.png`.

All test data was isolated and synthetic. Existing staged contents were preserved;
new corrections remain unstaged. No commit, push, deployment, or application or
production-data migration was performed.

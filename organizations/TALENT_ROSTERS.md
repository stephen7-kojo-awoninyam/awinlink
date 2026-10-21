# Organization talent tags and rosters

Organization roster affiliations are independent of staff/team memberships. They
do not grant login access, organization permissions, verification, or ownership.

Owners, managers, and recruiters can create roster entries and request profile
links using existing `MANAGE_RECRUITMENT` permissions. Viewers can read the private
roster and its history using `VIEW_TALENTS`. Platform admin flags grant no bypass;
inactive organizations and removed/suspended memberships lose access immediately.

Each entry has a display name, short talent details, a tag (e.g. Player or Alumni),
and an optional roster name (e.g. First team or 2026 cohort). These are plain text.
An omitted username creates an **UNCLAIMED** entry inside that organization only;
no account or TalentProfile is created. A manager can later link the entry to an
active talent username, changing it to **PENDING**. This is a nomination, not proof
that the talent owns the unclaimed identity. Only that account's talent can
**CONFIRM** or **DECLINE** the request. Confirmation explicitly agrees to the tag,
roster and details as shown. A declined or removed affiliation cannot be revived;
create a new request for fresh confirmation.

Only **CONFIRMED** entries for active organizations and active, public talent
profiles appear in profile badges and public organization rosters. Blocked
relationships are filtered for signed-in viewers. Unclaimed and pending entries,
private profiles, decision reasons and history never appear in public results.
Talent users can remove their own tag even when its organization is inactive.
Managers can remove entries while authorized. Removal changes status and appends
an event rather than deleting rows; badges disappear immediately.

Every create, link, response and removal writes an event in the same transaction.
Organization-first locking serializes transitions, and a partial unique constraint
prevents duplicate pending/confirmed tags for the same organization, talent, tag,
and roster. Repeated decisions are rejected without duplicate history. Linking
does not alter accounts, talent profiles, or existing staff permissions.

## Interfaces

Web: Organization dashboard → **Talent tags and rosters**, or the talent's own
profile → **Manage organization tags**. The workspace lets users choose an
organization, add entries, link usernames, confirm/decline, remove, and view history.
Confirmed badges link between talent and organization profiles.

Mobile: Profile → **Talent tags and rosters**. It uses the same API, permissions,
explicit removal confirmation, and history. Talent profiles show confirmed badges;
organization detail shows confirmed roster entries linked to talent profiles.

All API paths below are relative to `/api/organizations/`; authentication is
required, session writes enforce CSRF, and list/history responses are paginated
at 50 entries. Public here describes publication-consented data, not anonymous
API access. Server-rendered public organization pages can display those badges.

| Path | Methods and purpose |
| --- | --- |
| `roster-workspaces/` | GET accessible organizations and management capability |
| `<organization>/roster/` | GET private roster including closed entries; POST name, tag, optional roster, talent_details, username |
| `talent-tags/mine/` | GET the current talent's requests, affiliations and closed entries |
| `talent-tags/<id>/` | GET private history; POST action LINK/CONFIRM/DECLINE/REMOVE, optional username/reason |
| `talent-tags/profile/<talent>/` | GET published badges for a talent |
| `<organization>/roster/public/` | GET published organization roster |

## Migration and checks

`0012_talent_rosters` adds two tables, foreign keys, check constraints and a partial
unique index. It does not change or backfill existing rows or infer affiliations.
It supports PostgreSQL and SQLite. Apply it through the normal release process
before serving the new code. Do not reverse it after roster history exists;
rollback by retaining schema/data and shipping a compatible forward change.

Tests use `scripts/vc_audit.py`, which selects in-memory SQLite or an explicitly
configured loopback `awinlink_audit_...` PostgreSQL test database. Coverage includes
legacy row preservation, PostgreSQL concurrent decisions, organization scoping,
role revocation, CSRF, consent, visibility/blocks, duplicates, history, and web/mobile
UI actions. No production migrations or data changes are part of implementation.

### Local validation, 2026-10-21

- Focused PostgreSQL: 14 passed (11 API/web/permission tests plus 3 migration and
  concurrency tests), using a fresh loopback audit test database.
- Full mobile suite: 103 passed, 3 browser-dependent tests skipped. TypeScript
  passed. The 7 directly affected mobile/web interaction and profile tests also
  passed after the final UI changes.
- Django system checks, migration consistency (`makemigrations --check --dry-run`),
  `git diff --check`, and `git diff --cached --check` passed.
- Broader PostgreSQL organization/talent suite: 201 passed, 2 failed. The failures
  are the invitation tests in `organizations.tests.OrganizationTests` and
  `organizations.test_suspension.OrganizationSuspensionTests`. Existing
  organization and invitation URL definitions share `invite_talent` with opposite
  positional argument orders; the tests reverse with talent then opportunity,
  producing 404s when their IDs differ. Those existing routes were left unchanged.
- Broader SQLite suite: 194 passed, 3 PostgreSQL-only tests skipped, 6 existing
  membership migration tests errored while reversing marketplace 0004's
  PostgreSQL extension operation (`no such table: pg_extension`). The existing
  marketplace migration was left unchanged.

Existing staged work was preserved. Roster changes remain unstaged for review;
no commit, deployment, or application-database migration was performed.

### Routing and reversal follow-up, 2026-10-21

The regression findings above are now resolved. `invite_talent` names the
organization route with talent-first positional arguments. The existing
opportunity-first `/invitations/invite/<opportunity>/<talent>/` path remains
available under the distinct name `invite_talent_for_opportunity`. Both paths
still dispatch to the existing invitation workflow. Both recommendation templates
now pass named IDs; a stray incomplete link before the organization template's
`extends` tag was removed.

The installed Django `BtreeGistExtension` skips non-PostgreSQL connections when
applying, but its reverse implementation queries `pg_extension` without checking
the vendor. Marketplace 0004 now uses a local subclass with a PostgreSQL-only
reverse guard. PostgreSQL delegates to the original operation, preserving its
extension/router behavior. This correction belongs in 0004 because reversing a
later migration would still reach the original faulty reverse operation.

New regression tests use unequal talent/opportunity IDs, exercise both saved URL
paths and permission denials, render both recommendation templates, and reverse
and reapply 0004 with booking/history rows present. They verify unchanged rows and
restoration of the PostgreSQL exclusion constraint.

- SQLite organizations/talents/invitations/marketplace: 245 passed, 20 skipped
  (265 total), including the previously failing membership migration tests.
- PostgreSQL affected workflows: 24 passed, including the two original invitation
  failures, existing invitation response security, and migration/concurrency tests.
- Final routing/template regression rerun: 4 passed.
- Django checks, migration consistency, and both Git whitespace checks passed.
- A SHA-256 comparison of the complete staged diff confirmed that all staged
  work was unchanged. Follow-up corrections remain unstaged. All database tests
  used isolated audit databases; no commit, deployment, or application-data
  changes were performed.

### End-to-end roster audit

See [the 2026-10-21 audit report](../docs/roster-audit-2026-10-21.md) for subsequent
permission-refresh, blocked-link, protected navigation, independent personal
request loading, draft reset, public pagination, query-count, and responsive UI
corrections, together with real-browser and mobile/JWT HTTP evidence. Profile
affiliations now have previous/next links after 50 entries; a block prevents new
nominations/links from the acting manager or linked organization account. Web
**Refresh rosters** reloads both personal requests and organization capabilities.

### Phase 2 agreements

Confirmed claimed affiliations can now link to private transfers, sponsorships,
ambassador deals, and contracts. See [AGREEMENTS.md](AGREEMENTS.md) for required
parties, revision-bound consent, mutual ending, transfer atomicity, permissions,
history, UI paths, APIs and migration 0013. These records do not change staff
memberships or transfer existing agreements to another organization.

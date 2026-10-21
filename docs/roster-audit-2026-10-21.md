# Roster end-to-end audit — 2026-10-21

Audited organization rosters, unclaimed entries, profile linking, confirmation and
decline, publication, removal/history, authorization, pagination, and web/mobile
clients. All runtime fixtures were synthetic and used isolated local test
databases. Existing staged work was preserved; corrections remain unstaged.

## Findings corrected

1. **Mobile navigation:** `organization-rosters` was omitted from the protected
   navigator group. It is now registered with authenticated screens.
2. **Lost personal controls:** both clients coupled personal affiliation requests
   to the selected organization read. A revoked membership or failed roster read
   could hide the talent's own requests. Personal requests now load independently;
   a talent can still confirm, decline, remove and inspect their own affiliation
   after losing staff access.
3. **Workspace drafts and duplicate submissions:** switching organizations retained
   the previous draft. Both clients now clear it on a switch. Web controls are
   disabled during writes and successful creation resets the form. Closed web
   entries no longer offer an unusable reason input.
4. **Stale web permissions:** workspace capabilities were fetched only on initial
   load. Refresh now reloads them and clears inaccessible roster data; failed
   writes also refresh permissions. A visible refresh control makes new personal
   requests discoverable without reloading the page.
5. **Blocked requests:** a manager could nominate/link a talent despite a block.
   Both directions of a block between the talent and the acting manager or linked
   organization account now prevent new nominations and links. Denied operations
   leave the entry and history unchanged. Existing history/removal access remains.
6. **Silent public truncation:** server-rendered badges/rosters stopped at 50 with
   no way to reach later entries. Previous/next links now paginate visible,
   confirmed affiliations while retaining existing query parameters.
7. **Repeated authorization queries:** roster serialization recalculated the
   manager's permission for every row. It now resolves it once per organization
   per request. A query-count regression verifies that 50 rows do not repeat the
   permission lookup 50 times.
8. **Mobile-width web layout:** the browser capture revealed cramped inline fields.
   Scoped local CSS provides stacked full-width fields, wrapping long names, and
   controls at least 44px tall, including when external styles are unavailable.
   Native link/reason inputs also have visible borders and 44px minimum height.

## Verification

| Check | Result |
| --- | --- |
| Focused SQLite roster API/template tests | 15 passed |
| Broader SQLite organizations/talents/invitations | 213 passed, 5 PostgreSQL-only tests skipped (218 total) |
| PostgreSQL roster API, migration/concurrency, mobile JWT HTTP | 18 passed |
| Final PostgreSQL public pagination + mobile HTTP + real Chrome rerun | 3 passed; includes one mobile test repeated from the preceding run |
| Full mobile suite | 108 passed, 3 unrelated browser-dependent tests skipped (111 total) |
| Direct web/mobile roster regressions | 9 passed, included in the full mobile suite |
| Mobile TypeScript | Passed |
| Django system checks and migration consistency | Passed; no new migration required |
| `git diff --check` and `git diff --cached --check` | Passed |
| SHA-256 comparison of the complete staged diff | Unchanged from audit start |

The Chrome test uses the actual DOM and session/CSRF-authenticated requests to
Django's live test server backed by PostgreSQL. It exercises 51-entry pagination,
Unicode/HTML-like text, unclaimed creation, linking, confirmation, public talent
and organization profile badges, staff revocation, cancellation of removal,
removal/history, decline, outsider rejection, CSRF rejection, and a 390px viewport
with a form-width/control-height assertion. The initial startup attempt timed out;
a longer diagnostic startup wait and subsequent complete reruns passed.

The mobile HTTP test transpiles and drives the actual roster TSX screen and its
roster client using controlled React hooks and native component placeholders.
Requests use real JWT authentication against the isolated live PostgreSQL server.
It covers the lifecycle and loss of organization membership without losing the
talent's personal controls. Shared API-client tests cover token behavior; the
route-guard and late badge-response regressions run in the mobile suite.
This is screen-logic and HTTP validation, not an Android/iOS simulator or physical
device rendering test. Physical-device validation was not performed.

Reusable tests/scripts: `organizations/test_roster_e2e.py`,
`scripts/roster_browser_e2e.cjs`, and `scripts/roster_mobile_e2e.cjs`. Set
`ROSTER_TEST_CHROME` to a Chromium executable and `AWINLINK_AUDIT_POSTGRES_URL` to
an explicit loopback `awinlink_audit_...` database before invoking them through
`scripts/vc_audit.py test organizations.test_roster_e2e --noinput`.

The latest synthetic mobile-width browser capture is
`../.audit-roster-e2e/web-mobile-viewport.png` (an ignored local audit artifact).
No commit, deployment, or application/production data changes were performed.

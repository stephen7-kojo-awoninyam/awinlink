# Profile, block, email and draft-event remediation

Implemented locally for S05–S08. No deployment, real account updates, storage
deletions, live CDN migration or provider invalidation was performed. Existing
courses, profiles, legacy athlete records, relationships, notes, registrations,
consent/history records and files are preserved. No schema migration is needed.

## Profile visibility and blocks

Coach/scout API and web discovery, detail/view/follow/bookmark actions, saved lists,
notes and history now use the canonical active-account and bidirectional-block
scope. Recruiter workflows retain their public-profile restriction. Canonical
organization-only reads continue to require current organization VIEW_TALENTS
capability; a role label, staff flag or superuser flag does not override privacy.
Recruiter role checks read current database state before allowing interactions.

Hidden targets disappear from saved/history responses without deleting those
records. Owners can still remove their own follows/bookmarks. Bookmark updates
cannot reassign ownership or the target talent. Notes remain editable only on an
owned bookmark with a currently readable target. Personal and organization
recommendation candidates and saved discovery results recheck current visibility;
coach/scout analytics filter inaccessible talent references too. Existing tenant
workflow/roster consent rules continue to govern their separate records.

Legacy athlete pages use the linked TalentProfile's visibility when one exists.
A legacy-only profile is owner-only. Inactive owners are excluded. The legacy page
and media share this policy; no record is converted, deleted or silently published.

Profile-linked feed posts and their files cannot expose a hidden talent or draft
event through captions, nested objects, saved posts or shared-feed cards. The same
parent checks apply before feed interactions. Public unblocked profiles and
published-event posts remain readable under the existing post visibility rules.

## Public identity versus account email

Public talent payloads use an allowlisted PublicUserSerializer without login email,
including the talent owner's profile payload. Login, registration, Google login and
`/api/auth/me/` retain the authenticated account serializer and its email field.
Mobile PublicUser types are separate from the authenticated User contract.
Configured organization business contact fields remain available; login email is
not copied into a new public field and no contact-sharing consent is inferred.

## Event authorization

The shared event scope covers web/API detail, feedback, gallery, media, ordinary
interactions, discovery/recommendations and direct files. Child list reads validate
the parent even when no child records exist.

| Event state/context | Read policy |
| --- | --- |
| DRAFT | Current organization VIEW_EVENTS capability required |
| PUBLISHED | Active organization; active linked organizer account when present |
| CLOSED/CANCELLED | Authorized organization reader or an existing participant's history |

Management still requires MANAGE_EVENTS. Removed/suspended memberships, inactive
actors and suspended organizations cannot read drafts. Existing participants do
not gain draft access when an event returns to draft. Staff/superuser flags alone
do not grant organization permission. Legacy organizations without a linked login
can retain published-event visibility, but have no implicit owner login or draft
permission. Existing authorized members are evaluated by their capabilities.

Meeting links are returned as part of a readable event's existing payload,
including published events. This patch restricts draft authorization; changing
published-event joining to a registration-only policy requires its own explicit
product rule. Feedback, certificates and participant records are retained.
Historical certificate verification and owner history remain available without
revealing a hidden event's current title through certificate payloads or pages.

## Files and caching

Original/HEAD/Range delivery now checks owning records for canonical talent photos,
covers, achievements/certification files, legacy athlete photos/media, event images
and galleries. Orphan paths are denied without deleting bytes. New uploads in these
namespaces use authenticated Cloudinary storage; application URLs retain normal
authorized and published/public delivery. Provider URLs remain server-side.

The historical migration tool's strict private-prefix list now includes these
namespaces. Use a newly reviewed inventory for newly covered prefixes, not a
hand-edited old journal. Historical direct CDN URLs remain potentially exposed
until the [provider migration and CDN checks](verification-private-media.md) are
actually executed. This patch has not run them.

Viewer-dependent API/media/profile/event/feed responses use private, no-store
caching. Middleware also applies the policy to denial responses produced outside
view decorators, while preserving existing cache directives on hardened endpoints.
General account identity media is distinct from the protected talent/legacy/event
namespaces; this change does not redefine account identity as private profile data.

## Mobile behavior

Profile images and event galleries use authenticated image requests; gallery
videos use the existing authenticated player. Account/context-scoped state clears
restricted data on identity changes, including switching away and back before a
new response. Revoked event-management reads clear drafts and participants. Event
detail denial clears the detail/gallery/feedback and removes its cached list row.
Generation checks discard late results after newer loads, selection changes or
screen cleanup. In-flight API writes still require server-side permission checks.

These controls do not recall data a previously authorized user already downloaded.
Current permission changes take effect on subsequent server authorization checks;
this is not a remote erasure facility for previously delivered client bytes.

## Validation

New regressions cover all four talent categories, both block directions, current
role/activity checks, saved/history and note behavior, email contracts, legacy-only
and linked profiles, current organization capabilities, empty event children,
draft/public transitions, private original files, JWT/session access, provider-read
ordering, linked feeds, saved recommendations and mobile request/account races.

Tests use disposable SQLite data, temporary media and mocked provider transports.
No real user or provider asset was used. TypeScript, migration drift and whitespace
checks passed. Physical devices, real browser sessions and live CDN behavior were
not exercised. Browser-only suites remain skipped in the local Node run.

The affected-app regression run completed 443 tests with seven skipped. The final
120-test security/compatibility acceptance run also passed after certificate
verification and history hardening. The final
mobile suite completed 173 tests: 170 passed and three browser-only tests skipped.
All 25 focused mobile privacy/relationship checks passed, including account round
trips and replies from an earlier identity context.

Focused new backend tests:

```powershell
.venv\Scripts\python.exe -u -B scripts/test_security_phase1.py talents.test_profile_privacy events.test_privacy feed.test_linked_privacy recommendations.test_profile_privacy --fast
```

From `mobile/`, run `npm.cmd test` and `npx.cmd tsc --noEmit`.

# Remaining Medium and Low security work

For the reconciled release status, use the [final security release checklist](final-security-release-checklist-2026-10-28.md). Earlier counts/tables below are historical snapshots; subsequent resource, retention and other topic follow-ups must be read before treating a finding as still open or fully closed.

**Resource implementation update:** bounded collection APIs, account upload-byte
budgets, shared ingress/transcoding admission, and aggregate WebSocket limits are
implemented locally. See [resource hardening](resource-hardening.md) for client
compatibility, concurrency tests and release dependencies. Production capacity
calibration and lifetime storage-entitlement policy remain separate decisions;
these changes do not delete or re-inventory historical files. No deployment was
performed. Earlier tables below remain historical review snapshots.

**Admin/settings implementation update:** S10/S11 have now been remediated locally;
see [admin/production implementation notes](admin-production-hardening.md). Current
remaining Medium work is S09 (partial) and S12. Earlier tables and implementation
updates below are historical review snapshots. No deployment was performed.

**Implementation update:** S05–S08 have since been remediated locally; see
[profile/event implementation notes](profile-event-privacy-fix.md). The table below
records the pre-implementation review. Current remaining Medium work is S09
(partly remediated), S10, S11 and S12; S13 remains fixed locally. Historical CDN
execution is still pending. No deployment was performed.

Reviewed 2026-10-27 against the current local working tree, including the preceding
ADMIN, upload, portfolio and verification fixes. This is a review and implementation
plan: no application behavior, deployed configuration, live provider assets or
application data was changed. Findings describe local code, not verified production
exposure. Existing courses, profiles, relationships, evidence and files must survive
the proposed work unless a later, explicitly scoped erasure operation requires it.

## Current status and priority

Eight Medium findings remain open or partly remediated. The sole Low finding is
fixed locally. Priority below is implementation order, not a severity reclassification.

| Finding | Current status / evidence | Priority | Main dependency |
| --- | --- | --- | --- |
| S07: login email in public profiles | Open. `api/serializers.py:50` includes email; `:202` embeds it in talent profiles. Current-user and login responses reuse that serializer. | First privacy patch; small scope | Separate authenticated-account and public-summary contracts; mobile types |
| S05: coach/scout block bypass | Open. Discovery, follow, bookmark, view-history and web lookups use PUBLIC checks without the full active-account/block scope. Blocked coach read and scout follow reproduced. | First privacy batch with S06 | Canonical talent scope plus distinct interaction permission checks |
| S06: legacy athlete privacy bypass | Open. `athletes/views.py:86` serves a profile by ID without the canonical ACL; inactive/private owner's biography remains anonymously readable. | First privacy batch | Explicit rule for legacy-only profiles; legacy media ownership mapping |
| S08: unpublished event disclosure | Open. Detail/media/feedback bypass published-list scope; draft description, meeting link and media metadata reproduced. Web detail also fetches by ID. | Next privacy batch | Shared event visibility, organization capabilities, meeting-access policy, private media scope |
| S10: admin login limits | Open. Standard admin login bypasses `accounts/security.py`; three failed attempts survive a one-attempt fixture limit. Live edge protection is unknown. | First hardening batch; can proceed alongside privacy work | Shared auth limiter, trusted client-address policy, Redis integration checks |
| S11: implicit development mode | Open on unrecognized environments. Custom-host fixture still defaults to DEBUG=true without secure cookies. Actual production environment was not inspected. | First hardening batch; before any future release | Explicit mode contract for WSGI, ASGI, commands, workers and local development |
| S09: aggregate resource controls | Partly remediated. Per-file signature/size enforcement and a streaming per-request file-byte cap now exist. Unpaginated lists, per-account/tenant quotas, concurrent transcoding and account-wide socket budgets remain. | Following bounded-work batch | Client pagination compatibility, shared Redis primitives, isolated workload measurements |
| S12: retained uploads after deletion | Open. Fixture account deletion still leaves its upload. Private portfolio/evidence proxy reads now fail after reference deletion, reducing immediate disclosure without erasing bytes. Public namespaces/direct CDN copies remain a concern. | Design now; destructive execution last | Retention/hold decisions, ownership inventory, durable erasure jobs, typed provider operations, CDN work |
| S13: filename HTML sink | Fixed locally. `attachmentPreview.textContent` replaces innerHTML; existing preview regression passed. | Retain coverage; no new fix needed | Optional real-browser smoke test; no production dependency |

The earlier High CDN condition is **not closed**: a safe migration tool exists, but
no live migration or invalidation was executed. It remains a separate release gate
and must not be obscured by completion of this Medium/Low plan. See
[verification/CDN remediation](verification-private-media.md).

## Proposed implementation batches

### 1. Public identity minimization — S07

Add an explicit allowlisted public user summary. Keep email and account-edit fields
in the self/account serializer used by login, registration, Google login and
`/auth/me/`. Use the public summary in talent profiles and trace every nested
consumer: coach/scout views and saved lists, recommendations, search and profile
details. Do not replace a separately published organization contact address merely
because its field is also named email.

Update `mobile/src/types.ts`: a public profile user must not be typed as the full
authenticated User. Keep account/profile editing functional. Do not copy login
email into a public contact field or infer consent from an existing value. A new
consented public-contact feature can be a later additive change; it is not needed
to remove this leak.

Acceptance: unrelated viewers never receive login email at any nesting depth;
auth/self responses retain their contract; all four talent categories render on
web/mobile without email; existing organization public contacts remain intact.
No database migration or profile-data rewrite is required for the removal.

### 2. Talent visibility and interaction consistency — S05/S06

Reuse `talents/visibility.py` and `accounts/safety.py` across coach/scout directories,
detail/view/follow/bookmark writes, dashboards, recommendations and saved/history
reads. Require current active actors and owners. Audit all duplicate web/API routes,
not just the two reproduced endpoints. Read visibility must not grant write or
recruiter privileges. Preserve public-only restrictions on workflows that currently
support only public profiles; reusing the broader helper must not accidentally
enable organization-only access or remove organization capability checks.

Retain relationship/history rows. Hide inaccessible nested personal data after a
block, privacy change, role change, suspension or membership revocation. Permit
safe removal of one's own follow/bookmark without disclosing the hidden target.
Prevent new interactions when either side blocks the other. Recheck permissions
before side effects and notifications; exercise block/mutation races where needed.
Clear cached screen data on account/profile changes and failed authorization.

For legacy athlete pages with a TalentProfile, enforce the same owner's canonical
visibility. Prefer a permission-checked redirect to the canonical profile if it
preserves intended legacy content. For legacy-only accounts, the safe proposed
default is owner-only until visibility is explicitly established; record and approve
that product policy before implementation rather than treating missing data as PUBLIC.
Preserve AthleteProfile, achievements and media records and both URL ID namespaces.

Apply the legacy policy to file delivery too. `athletes/profile/`, `athletes/cover/`
and `athletes/media/` are currently unconditional public namespaces in
`config/media_views.py`. Identify ownership and references before changing them;
new restricted uploads need authenticated provider storage and old direct links
need a reviewed migration scope. A page ACL alone cannot close the media route.

Acceptance: owner access, active unblocked public access, authorized organization
access where supported, no new admin bypass, both block directions, inactive actors
and targets, role/membership revocation, legacy-only and dual-profile accounts,
saved/history views, mutation side effects, and web/session/JWT/mobile parity.

### 3. Event visibility, participation secrets and files — S08

Introduce shared event read predicates for web/API list, detail, media, feedback and
gallery. Published visibility requires an active organizer and applicable active
owner policy. Drafts require current organization VIEW_EVENTS capability; management
still requires MANAGE_EVENTS. Do not substitute an ORGANIZATION role label or stale
membership for either capability. Check the parent even when child lists are empty.

Separate public event data from participation credentials. The proposed rule is
meeting links for authorized organizers and eligible current participants only;
precise eligible statuses must follow the approval/registration policy. Resolve
whether these links were intentionally public before changing that product contract.
Regardless of that decision, unrelated users must not receive draft meeting links.
Review participant and feedback serialization alongside the public-summary change.

`events/images/` and `events/gallery/` currently allow public file delivery; fixing
the serializers will not protect those bytes. Add parent-aware ACLs and authenticated
storage for new files, retain authorized published-event delivery through the app,
and extend the historical migration's strict namespace allowlist and tests. The
current migration does **not** include event or legacy athlete namespaces. Do not
run a broad rename until their reference mapping and target policies are reviewed.

Acceptance: published/draft/cancelled states, owner/member/outsider, suspended
organization and revoked member, participant approval/cancellation, empty children,
web/session/JWT, meeting-link absence in nested payloads, direct file GET/HEAD/Range,
provider-read ordering, and anonymous/published-file policy. Preserve registrations,
feedback, certificates and media. Historical CDN closure remains operational work.

### 4. Privileged login and explicit environment mode — S10/S11

For S10, wrap or customize admin login while preserving the existing admin registry,
URL names, CSRF, staff checks and legitimate admin access. Apply the shared IP and
normalized-identity limits before credential checks, across all admin login paths.
Avoid a fresh budget merely by switching between main and admin login. Return
controlled 429/Retry-After and no-store responses; unavailable required shared
protection must return a controlled 503, never allow unlimited attempts. Do not
introduce an indefinite account lock that attackers can use to lock out admins.

Acceptance: CSRF-valid budget exhaustion, normal successful staff/superuser login,
nonstaff denial, spoofed forwarded-IP attempts under the trusted-proxy model,
counter expiry, Redis outage, and concurrent attempts across two workers. Use real
isolated Redis for sharing/atomicity checks. MFA/SSO, edge restrictions and an
operator recovery path are separate operational hardening; do not block the local
rate-limit fix waiting for an identity-provider rollout or change credentials here.

For S11, establish an explicit development/test/production contract. Deployed
WSGI/ASGI and worker/command entrypoints must fail closed without the required mode
and production secrets/settings; local development must be deliberate. Keep
Railway/Render guards. Update test settings, examples and startup documentation
without editing `.env` or hosted configuration. Cover all release entrypoints so
HTTP cannot be secure while background commands silently use development defaults.

Acceptance: clean subprocess settings matrix for missing/invalid modes, custom
hosts, Railway/Render, explicit local development and tests; production DEBUG cannot
be enabled, weak secrets fail, intended hosts/origins/cookies/HTTPS are configured,
and Redis requirements are enforced. Check proxy-header trust separately; never
assume a client-provided forwarded header is authoritative. Existing HSTS preload
and subdomain settings need a domain-readiness review before any rollout.
Run `check --deploy` with synthetic production settings now and, only during a
separately authorized release, the actual release environment. This follows
[Django's deployment checklist](https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/).

### 5. Bounded collection, storage and socket work — S09

Split this into independently reviewable changes; do not replace existing upload
validation, frame bounds, credential watchdogs or Rising Talent job safeguards.

* Pagination: inventory custom APIView and generic lists plus all web/mobile consumers.
  `api/views.py:228` still exposes an unpaginated talent queryset, and
  `mobile/src/components/DirectoryScreen.tsx:73` expects arrays. Choose a documented,
  bounded contract; use explicit/versioned pagination negotiation while updating
  supported clients, not a surprise global array-to-object response change. An
  unbounded legacy fallback cannot be the final state. Avoid silent truncation and
  client helpers that automatically load every page. Use stable indexed ordering,
  bounded filters, page-size caps, page-level prefetches and query budgets. Regular
  APIViews require explicit paginator calls; see
  [DRF pagination](https://www.django-rest-framework.org/api-guide/pagination/).
* Upload/processing budgets: retain current per-file and per-request streaming
  caps. Add atomic account/organization byte reservations with TTL/reconciliation,
  bounded concurrent uploads and controlled transcoding concurrency. Existing
  `playback_copy` has a 60-second timeout and one ffmpeg thread but no shared
  concurrency fence or duplicate-work lock. Select duration/dimension, processing,
  storage and quota limits from isolated workload measurements. Durable queued work
  needs an explicit retry/recovery runner; do not assume a queue framework exists.
* WebSockets: add shared per-account connection leases and aggregate rate budgets
  across messaging, call and classroom socket types, keeping existing per-connection
  limits and expiry/revocation. Acquire atomically before expensive group work;
  release on errors/disconnect, renew bounded leases and expire crashed workers.
  Same-account token refresh must not allocate a second budget. Define limits to
  support legitimate multi-tab and mobile calls and protect reconnect storms.

Dependencies: shared Redis, trusted edge identities, small isolated PostgreSQL/Redis
fixtures, documented client compatibility and observability. Tests must prove
bounded rows/query counts, invalid cursor handling, no duplicated results in normal
stable ordering, quota races and failed-upload release, duplicate transcoding
requests, cross-worker sockets, worker crashes, and outage behavior. Do not choose
strict aggregate budgets using process-local counters or ordinary non-atomic cache
read/modify/write. Keep load tests bounded and off production.

### 6. Auditable account-file erasure — S12

Begin with a read-only reference/ownership inventory and retention/hold decisions.
The destructive stage depends on those decisions; inventory and job design can
proceed now. Include local/cloud originals, derivatives, playback caches, shared
organization/message/course assets and backups under their separate retention rules.
Account deletion must not erase organization-owned or still-shared files merely
because the deleted account uploaded them.

Before deleting database rows, capture eligible asset identities in a durable
erasure job/outbox in the same transaction. Dispatch after commit, but do not rely
on an in-memory on_commit callback alone: a worker/scheduler must recover pending
jobs after crashes. Deny user access and revoke applicable credentials promptly;
physical erasure may be asynchronous with visible pending/failed/completed status.

The 30-day retention implementation now adds durable jobs when portfolio/event
media is removed or replaced, audited superuser legal holds, all-model shared
reference checks, and an explicit dry-run-first erasure command. See
[media-retention-30-day.md](media-retention-30-day.md). It does not run any cleanup.
Cloudinary queue entries stay unresolved until a superuser verifies exact provider
metadata. The media-deletion audit added an explicit Cloudinary deletion primitive that checks
the immutable `asset_id`, resource type, and delivery type, then requests CDN
invalidation. The inherited untyped Cloudinary `delete(name)` now fails closed.
Portfolio and event deletion endpoints immediately revoke app access and enqueue
physical retention work. The queue's `READY` state is separate from erasure; the
command requires `--apply` and rechecks eligibility. Provider permission/rate-limit
errors must never be reported as successful erasure.

Use the CDN migration manifest as evidence of delivery-type changes, not as an
automatic deletion list. Minimize and expire erasure audit data and align backup
expiry/restore behavior so deleted accounts are not silently reintroduced. Record
retention exceptions instead of claiming complete erasure. Keep physical cleanup
disabled until those controls and a product retention policy exist.

Acceptance: transaction rollback, crash after commit, duplicate jobs, partial
provider failure, already-missing objects, shared references, holds, authenticated
and legacy provider assets, derivatives, CDN pending state, and data-preserving
dry-run reports. Product/retention decisions must precede destructive execution;
this plan does not establish a legal retention period.

## Dependencies and closure gates

| Work | Can start without other fixes | Required before closure |
| --- | --- | --- |
| S07 summaries | Yes | Self/public API and mobile contract tests |
| S05/S06 | Shared policy audit now | Legacy-only visibility decision; page and file ACLs; nested payload checks |
| S08 | Event parent ACL now | Meeting policy; private event media and reviewed CDN scope |
| S10 | Local login wrapper now | Shared Redis/concurrency tests; operational edge/MFA evidence tracked separately |
| S11 | Environment contract now | Every entrypoint tested; future release environment evidence |
| S09 | Inventory/instrumentation now | Updated client pagination contract; shared counters/leases; isolated capacity evidence |
| S12 | Ownership inventory/outbox design now | Retention/hold policy; typed storage operations; shared-reference checks and explicit erasure execution scope |
| S13 | No new fix | Keep regression; browser smoke adds confidence |

Each implementation batch needs negative authorization tests before its patch,
positive legitimate-use tests, then web/mobile compatibility checks as applicable.
Move affected assertions out of the audit characterization module into owning-app
security acceptance suites, reversing the vulnerable expectations; do not weaken
the original tests just to obtain green results. Re-run prior ADMIN, upload,
portfolio and verification tests after touching shared policy/storage/auth code.

Prefer additive schema changes for quotas/outbox/legacy visibility; review migration
plans against disposable data before any real database operation. Preserve API
compatibility intentionally. If a later rollback is needed, keep restrictive server
ACLs and private storage in place; use a forward compatibility fix or disable the
affected feature rather than restore public email, draft access or public delivery.
No rollback may silently republish migrated files. Deletions are irreversible and
need a completed dry-run/reference review before execution.

## Review validation and limitations

Fresh isolated characterization run: **8 tests passed**, confirming vulnerable
behavior for S05/S06/S07/S08/S10/S11/S12; S05 has two reproductions. These passing
tests prove the findings remain open, not that the behavior is safe. S09 was
reviewed in source; no stress/load test was performed. The existing mobile
upload-security file ran **8 tests, all passed**, including the S13 textContent
regression. That regression is a source assertion, not a real-browser exploit test.

Commands used:

```powershell
.venv\Scripts\python.exe -u -B scripts/test_security_phase1.py scripts.security_audit_reproductions.OpenSecurityFindingReproductions scripts.security_audit_reproductions.OpenConfigurationFindingReproductions --fast
# From mobile/
node --test tests/upload-security.test.cjs
```

All database deletions and uploaded-file checks used disposable fixtures. No real
user/file inventory, provider mutation, production settings change, dependency
installation, browser/device session, Redis load test or deployment was performed.
Production proxy, admin edge/MFA and infrastructure controls remain unverified.

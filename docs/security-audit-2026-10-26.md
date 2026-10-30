# Awinlink security audit — 2026-10-26

Consolidated current local status and unresolved operational gates: [final security release checklist](final-security-release-checklist-2026-10-28.md). Preserve the findings below as historical evidence; later remediation does not establish live production verification.

**Admin/settings remediation update:** S10/S11 are fixed locally through a shared
admin/ancillary login budget and production-by-default settings with Railway
compatibility. See [admin and production hardening](admin-production-hardening.md).
Remaining Medium work is S09 (partial) and S12. No deployment or live configuration
change was performed; historical CDN execution also remains pending.

**Profile/event remediation update:** S05–S08 are now fixed locally, covering
profile/block scopes, legacy athletes and media, public login-email removal, and
draft-event parent/file authorization. See [implementation and regression notes](profile-event-privacy-fix.md).
Four Medium findings remain open/partial: S09–S12. Historical CDN migration remains
pending operational execution; no deployment was performed.

**Medium/Low review (2026-10-27):** eight Medium findings remain open or partly
remediated; S13 is fixed locally. Fresh characterization checks confirm remaining
vulnerable behavior. See the [prioritized implementation plan](security-medium-low-plan.md)
for current evidence, dependencies, policy decisions and acceptance gates. This is
a documentation review, not deployment or further application remediation.

**Remediation update:** S01 has since been fixed locally in registration/onboarding
validation and covered by `accounts/test_role_security.py`. Existing administrators
were preserved; no data migration or deployment was performed. The findings and
counts below describe the original audit snapshot. See
[ADMIN escalation fix](admin-role-escalation-fix.md) for the change and validation.

**Upload remediation update:** S02 and the filename preview sink S13 have since
been fixed locally. New verification uploads in S04 now use authenticated storage;
historical direct provider URLs still require a separately authorized migration.
See [upload and file delivery hardening](upload-security-fix.md). The original
audit evidence below remains a historical record.

**Portfolio remediation update:** S03 has since been fixed locally across web,
mobile, APIs and application media delivery. See
[portfolio authorization remediation](portfolio-authorization-fix.md) for the
access policy, regression tests and historical direct CDN URL limitation.

**Historical media remediation update:** S04 now also has current owner/reviewer
authorization checks, referenced-object enforcement, and a journaled migration
tool for historical public/private CDN delivery types. The provider migration has
not been run; historical CDN exposure remains pending operational remediation.
See [verification and historical CDN remediation](verification-private-media.md).

This is an audit of the current local working tree, including the uncommitted
course, roster and Rising Talent work. **No deployment, production configuration
change, production data access, live attack, or application fix was performed.**
Only this report and an isolated reproduction module were added. Existing course
data and prior changes were preserved.

## Assessment

**Do not release this tree before addressing S01.** A regular account can promote
itself to the application ADMIN role and disable another account. CSRF protection
does not prevent this authorized-session attack. The existing security regressions
do not cover this onboarding path.

There are **13 ranked findings: 1 Critical, 3 High, 8 Medium, 1 Low**. Severity is
based on demonstrated impact and prerequisites, rather than an unverified CVSS
number. Deployment-dependent conditions are stated explicitly. A passing audit
reproduction confirms an open finding; it does not mean the application is secure.

| ID | Severity | Finding | Evidence |
|---|---|---|---|
| S01 | Critical | Self-service onboarding permits ADMIN privilege escalation | CSRF-valid session reproduction, including disabling another fixture account |
| S02 | High | HTML uploaded as video is served inline on the application origin | Local-storage upload and anonymous original-file HTTP response reproduced |
| S03 | High | Private and organization-only portfolios bypass profile authorization | Private, organization-only, detail and blocked-user reads reproduced |
| S04 | High | Verification documents omit private Cloudinary delivery | Mocked upload confirms no authenticated delivery type; source confirms missing ACL route |
| S05 | Medium | Coach/scout discovery and interactions bypass account blocks | Blocked coach reads profile/email; blocked scout follows again |
| S06 | Medium | Legacy athlete page ignores privacy and inactive accounts | Anonymous read of an inactive private owner's legacy biography reproduced |
| S07 | Medium | Public profile APIs disclose account login email | Unrelated account reads nested user email |
| S08 | Medium | Unpublished event details and media are readable by unrelated accounts | Draft absent from list but detail, meeting link and media are returned |
| S09 | Medium | Resource controls do not bound aggregate work | Source: unpaginated collections, unchecked file sizes, per-socket rather than per-account budgets |
| S10 | Medium | Django admin login bypasses configured authentication limits | CSRF-valid repeated attempts ignore a configured one-attempt budget |
| S11 | Medium | Non-Railway/Render deployments can default to development security | Isolated custom-host configuration keeps DEBUG on and secure cookies unset |
| S12 | Medium | Account deletion retains uploaded files | API deletion removes fixture account/rows but leaves fixture file in storage |
| S13 | Low | Selected attachment filenames enter an HTML sink | Source: filename strings are joined into innerHTML; victim file selection is required |

## Findings and corrective work

### S01 — Critical: unrestricted role changes grant application administration

`onboarding/views.py:35` is the effective, second definition of `choose_role`.
It takes `request.POST['role']` through `.get()`, assigns `request.user.role` at
line 41, and saves without using `RoleSelectionForm`, validating choices,
restricting role transitions, or requiring existing administrator authority.
`onboarding/urls.py` exposes it at `/onboarding/role/`.

An ordinary logged-in user can submit ADMIN with a valid CSRF token. The fixture
account then accesses `/api/role-models/` (previously 403) and successfully toggles
another account inactive via `/dashboard/users/toggle/<id>/`. The attacker's
`is_staff` and `is_superuser` both remain false. This is application administrator
escalation, not proof of access to Django's separate `/admin/` site or arbitrary
server execution.

Impact extends to consumers of the role field: user and talent management,
verification moderation, course moderation, role-model management, and competition
administration. Examples: `dashboard/views.py:252`, `dashboard/views.py:285`,
`api/views.py:5396`, `learning/api_views.py:CourseApproveAPIView`, and
`competitions/services.py:26`. Existing sessions can use the changed database role.

**Fix first:** remove privileged role assignment from onboarding; explicitly
authenticate and validate allowed initial roles and permitted transitions. Base
platform administration on a server-controlled authority separate from a public
profile category. Audit every ADMIN shortcut. Add negative tests for every public
onboarding/registration/profile mutation, plus end-to-end checks that a normal
account cannot reach moderation after such mutations. Review historical ADMIN
assignments and session exposure through an authorized incident review; do not
blindly remove legitimate administrators.

### S02 — High: stored HTML execution through local video media

`feed/models.py:137` uses an unrestricted FileField for video.
`feed/api_views.py:PostCreateAPIView` and `feed/serializers.py:PostSerializer`
accept a file named `.html` with HTML contents as video. The ACL-protected original
asset route in `config/media_views.py:152` selects MIME type from the filename at
line 187 and returns a FileResponse with **inline** disposition. The normal
`?playback=mp4` URL does not protect the original: its query can be removed.

The local reproduction uploads a harmless script marker, then obtains the exact
bytes anonymously from a public post's original asset with `Content-Type:
text/html` and inline disposition. A browser navigation to that app-origin HTML
can execute script with that origin's privileges. HttpOnly cookies do not prevent
same-origin authenticated requests. The reproduction verifies HTTP delivery; it
does not execute a browser exploit or access another user's session.

**Condition:** confirmed with LocalPlaybackStorage, which is selected when cloud
credentials are absent. Cloudinary video ingestion was mocked/not attacked, so
this report does not claim the same upload succeeds there. Similar unvalidated
FileFields in messaging and learning require review.

**Fix:** validate actual allowed media containers, sizes and types; reject active
content. Serve originals with a safe type and attachment disposition where needed,
prefer a separate untrusted-media origin, and add a restrictive response CSP as
defense in depth. Test original URLs as well as transcoded URLs.

### S03 — High: portfolio object authorization is missing

`portfolio/api_views.py:130` fetches an item by ID and returns it to any
authenticated user. `portfolio/api_views.py:262` fetches a talent by ID and returns
all portfolio items. Neither uses `talents/visibility.py:visible_talent_profiles_for`.

Four reproductions demonstrate private profile, organization-only profile,
individual item, and blocked-account reads. The main `/api/talents/<id>/` endpoint
returns 404 for the same viewer, while the portfolio endpoints return 200 with
private descriptions. IDs are enumerable; being logged in is the only prerequisite.

**Fix:** resolve each owning talent through the same visibility, active-account,
organization capability and block policy before serialization. Preserve owner
access and intended authorized organization access. Review public CDN portfolio
file delivery separately: endpoint ACLs cannot revoke a public file URL.

### S04 — High: sensitive verification uploads are outside private storage policy

`talents/models.py:340` stores verification documents under
`verification_documents/`. That prefix is absent from
`config/media_storage.py:22`. `_upload` at line 41 sets authenticated delivery only
for listed prefixes, and `_get_url` at line 57 delegates other assets to ordinary
Cloudinary delivery. The verification management template links directly to
`request.document.url`. There is no verification-document authorization branch
in `config/media_views.py` or production local-media URL mapping.

The mocked upload test confirms that verification document uploads omit the
authenticated delivery type. With configured Cloudinary storage this leaves proof
documents on ordinary upload delivery, accessible to anyone possessing their URL.
The audit did not enumerate real documents, establish their contents, or request a
real CDN URL. Local production storage instead lacks an authorized serving route
for these documents; that is not evidence of local anonymous disclosure.

**Fix:** upload verification evidence privately from the start; expose it only
through an owner/reviewer authorization check with no-store and safe download
headers. Inventory and migrate existing objects, including CDN invalidation where
applicable. Test unauthorized, revoked reviewer, inactive user and deleted-object
access. Do not regard a difficult-to-guess filename as authorization.

### S05 — Medium: block policy is inconsistent in coach/scout workflows

`coaches/api_views.py:104` filters public visibility but omits blocked users and
active talent accounts. Scout and coach view/follow/bookmark flows similarly rely
on public visibility; see `scouts/api_views.py:130` and `:208`. The corresponding
web views also use direct public-profile lookups.

A blocked coach still receives the blocked talent and login email through the
coach list. A blocked scout successfully creates a new ScoutTalentFollow. This
does not prove they can send a message or enter a call; those have separate checks.

**Fix:** use the canonical visible-talent scope for discovery and enforce current
bidirectional blocks on each interaction, including web routes and saved/history
views. Scope any allowed historical access explicitly. Verify inactive owners do
not reappear through secondary lists.

### S06 — Medium: legacy athlete route bypasses privacy

`athletes/views.py:86` serves an AthleteProfile by ID without authentication,
account status, block or associated TalentProfile visibility checks. Its template
renders biography, achievements and gallery/performance information. The fixture
test confirms an anonymous user reads a legacy biography even when the same
owner has a PRIVATE talent profile and is inactive. This requires a legacy
AthleteProfile to exist; the audit did not count such profiles in production.

**Fix:** align legacy routes with the canonical profile ACL, or retire them through
a permission-checked redirect. Define explicit visibility for legacy-only accounts
rather than making privacy depend on which profile URL is used.

### S07 — Medium: account email is serialized as public profile data

`api/serializers.py:50` includes email in UserSerializer. TalentProfileSerializer
embeds that serializer at line 202 for other people's profiles. The same serializer
is useful for `/auth/me/` but exposes login contact information when reused for
discovery. An unrelated fixture account receives the public talent's email.
There is no separate public contact consent/field in this serialization path.

**Fix:** separate self/account serialization from public user summaries. Publish
only a separately configured contact address when the owner has chosen to share
it. Cover every nested use, including recommendations and recruiter lists.

### S08 — Medium: unpublished event data bypasses list visibility

`events/api_views.py:70` returns any Event to an authenticated caller by ID; its
queryset omits the PUBLISHED and active-organizer filters used by EventListAPIView.
`EventMediaListAPIView` at line 926 and `EventFeedbackListAPIView` at line 850
likewise query by event ID without checking parent visibility. EventSerializer
includes the meeting link.

The reproduction confirms an unrelated account sees a draft's internal description,
meeting link and media although that draft is absent from the public event list.
No live meeting was contacted. Whether published meeting links should also require
registration is a product policy decision that should be made explicit.

**Fix:** share one event visibility predicate across detail/media/feedback and
web/API routes; use organization capabilities for draft access. Gate meeting
credentials separately when participation is intended to be restricted.

### S09 — Medium: aggregate resource abuse remains insufficiently bounded

This is a source-verified capacity exposure, **not a destructive load-test result**.

* `api/views.py:228` serializes every visible talent with multiple prefetched
  collections. Several APIView lists have no pagination; DRF defaults in
  `config/settings.py:400` do not configure it. Merely adding a default paginator
  will not paginate custom APIView methods automatically.
* Media FileFields lack per-file type/size/duration quotas. Django's upload memory
  threshold is a disk-spooling threshold, not a maximum accepted file size.
* `messaging/consumers.py:324` accepts multiple authenticated user sockets without
  an account-wide connection quota. `messaging/socket_security.py:71` budgets frames
  per connection, so parallel connections multiply that budget. Each connection
  also performs periodic credential/database checks. Classroom signaling has
  stronger presence fencing but does not replace an edge-wide connection budget.

**Fix:** bounded cursor pagination and query budgets, per-account/organization
upload quotas, streaming size enforcement, controlled media processing queues, and
shared connection/rate/concurrency limits at application and proxy layers. Preserve
the existing frame limits and revocation checks. Measure realistic workloads on
isolated PostgreSQL/Redis infrastructure before selecting limits. An upstream
proxy may already provide some controls; that configuration was not inspected.

### S10 — Medium: privileged Django admin login is unthrottled in app code

`config/urls.py` mounts the standard `admin.site.urls`. The custom authentication
limiter in `accounts/security.py` is called by user/API login flows, not the Django
admin login. A CSRF-valid test submits three failed admin logins with the configured
login budget set to one; all receive ordinary 200 failure forms rather than 429.
This does not bypass passwords or Django staff permission checks.

**Fix:** apply shared brute-force protection to admin authentication, use stronger
administrator authentication such as MFA/SSO, and restrict admin exposure where
appropriate. Confirm any existing edge control before declaring a live exposure.

### S11 — Medium: insecure development defaults on unrecognized deployments

`config/settings.py:61` defaults DEBUG to true unless Railway or Render markers
are present. The strong secret check, HTTPS redirect and secure cookie defaults
therefore depend on an operator setting DEBUG=false outside those platforms.
A custom allowed hostname alone does not trigger production security. The isolated
configuration test confirms this fallback, without reading or changing live env.

**Fix:** make production mode explicit and fail closed for deployed entrypoints;
opt into development deliberately. Keep existing Railway/Render DEBUG guards and
strong-secret validation. Run Django deployment checks against the actual release
environment before a separately authorized deployment.

### S12 — Medium: deleting an account does not erase its stored uploads

`accounts/mobile_api.py:83` checks password and organization ownership, then calls
`user.delete()` at line 92. Database cascade deletion does not remove FileField
objects. No matching storage-erasure workflow was found. The isolated test deletes
an account through the API and confirms its uploaded portfolio file still exists.
For already public cloud assets, deletion of rows cannot revoke known file URLs.

**Fix:** define retention requirements, enqueue idempotent storage cleanup with
retries, handle shared objects carefully, and maintain an erasure result trail
without retaining unnecessary personal data. Verify local/cloud originals and
derivatives. Do not perform a blanket production storage deletion.

### S13 — Low: filename HTML injection in message attachment preview

`messaging/templates/messaging/conversation.html:1341` through `:1369` reads selected
File names and inserts them using `attachmentPreview.innerHTML = files.join(...)`.
An HTML-bearing filename can become markup. Exploitation requires the victim to
select a crafted local filename that their OS/browser permits; remote message
content alone is not shown to reach this sink. Windows filename restrictions limit
this path but do not make the cross-platform sink safe. This finding is a source
review, not a browser reproduction.

**Fix:** create text nodes and explicit line breaks, or set textContent. Add a
browser test with HTML-like filenames on supported platforms. A site CSP would
provide additional protection but is not a replacement for fixing the sink.

## Coverage and controls that were reviewed

The installed-app inventory contains 36 local Django apps. URL configurations,
views/serializers and common authorization helpers were inventoried; high-risk
paths received deeper review and isolated tests. This is not a claim that every
line or all business workflows were exhaustively proven secure.

| Surface/apps | Review focus and result |
|---|---|
| accounts, onboarding, dashboard, api | Registration/login, Google OIDC, password recovery, JWT/logout, deletion, administrator boundaries. S01, S07, S10, S12. |
| organizations, applications, invitations, opportunities, recruitment, shortlists | Tenant capabilities, owner/member/revoked/suspended scope, consent, roster history and workflow authorization. Existing permission regressions exercised. S01 still compromises separate platform-admin shortcuts. |
| talents, athletes, portfolio, scouts, coaches, search, analytics | Canonical visibility versus secondary routes, blocks, nested data, legacy profiles. S03, S05, S06, S07. |
| sports, science_technology, art, others, skills, domains | Category-profile owner setup, classification forms, shared profile/serializer exposure. Skills' TalentSkillsAPIView lacks the canonical ACL in source, but is not mounted by the current root URLconf; it is not counted as an exposed endpoint. |
| feed, connections, messaging, notifications | Post ownership/associations, CSRF/mutation methods, conversation/call membership, push destinations, token registration, WebSocket delivery. S02, S09, S13. |
| learning, competitions, events | Creator/host/judge/moderator access, enrollment, private lessons, classroom signaling and published/draft boundaries. S01, S08, S09. |
| marketplace, advertising | Participant/tenant checks, record-only financial state, webhook HMAC and server-side payment verification. Existing payment regressions exercised; no real transaction performed. |
| recommendations | Interest consent and current Rising Talent privacy/delivery/deduplication design reviewed against the existing dedicated audit. No intelligence job was run against application data. |
| core, clubs, performance | Root/public routing, shared feed scope and mutation regression coverage; clubs/performance views are stubs. |
| config and mobile | Production mode/secret/HTTPS/cookie defaults, media storage/proxy, native credential storage, token refresh fencing, same-origin media auth, socket renewal, release URL validation. S02, S04, S09, S11, S12. |

Positive controls present in this tree include default authenticated DRF permissions,
session CSRF checks, password validation, shared authentication rate limits that
fail closed without the required shared backend, strong-secret checks in declared
production mode, password-bound JWT validation, refresh-session revocation,
Google code/state/nonce/PKCE checks, permission-checked tenant services, and private
media prefixes for feed/message/lesson assets. These do not cancel the findings.

WebSockets use browser origin validation; authenticated native header-based JWT
sockets without an Origin are deliberately supported. User/call consumers recheck
credentials, JWT expiry and session revocation; call and classroom access use
current membership. Frame bounds and per-connection rate limits exist. No separate
cross-tenant socket-access bypass was confirmed in the audited paths. S09 remains
an aggregate capacity gap. No live WebSocket service was contacted.

## Validation

All fixtures used isolated test databases and temporary/in-memory media. Cloudinary
upload behavior was mocked. Mobile checks used local code and fixtures.

* New audit module: **16 tests passed**, covering open behavior and a separate established
  WebSocket expiry control. Run:
  `.venv\Scripts\python.exe -u -B scripts/test_security_phase1.py scripts.security_audit_reproductions --fast`.
  These are explicitly characterization tests, not acceptance tests for safe behavior.
  Change their assertions and migrate them into owning app suites when fixing issues.
* Existing focused backend suite: **192 run; 188 passed, 3 skipped, 1 failed**.
  It covers authentication/Google/logout, organization permissions, call/classroom
  security, media, push, posts, search, payments, invitations, CSRF and mutations.
  The failure is
  `messaging.test_socket_revocation.SocketRevocationTests.test_expired_idle_socket_is_closed_without_client_activity`:
  its one-second token was rejected before the connection assertion. A subsequent
  focused run reproduced that setup failure. The separate audit control loads ASGI
  before minting a five-second token, confirms successful connection, and verifies
  closure with code 4001 at expiry. No application change was made to mask the
  failing regression; the original test still needs a reliable setup window.
* Mobile: **14 tests passed** for socket credential renewal, Google flow,
  production release validation and same-origin media credential handling.
* No destructive load test, real browser exploit, native device test, new advisory
  database scan, live proxy/header test, or production secret/permission review was
  performed. Existing dependency audit JSON files and prior production reports were
  not treated as fresh proof of today's deployed state.

## Deployment-dependent risks and follow-up evidence

* **Legacy public Cloudinary media:** `config/media_views.py:97` retains a fallback
  to public upload assets. New private-prefix ACLs cannot revoke old direct CDN URLs.
  Previous reports acknowledge this migration gap; current cloud inventory and
  exploitability were not checked. Treat it as a potentially high confidentiality
  risk until asset migration is verified. It is separate from S04's new-upload policy.
* **Actual production settings:** hosted DEBUG/secret/HTTPS protections exist in
  source, but deployed revision, environment, proxy header overwrite, Redis sharing,
  DB/Redis transport security, storage configuration and admin edge controls were
  not verified. In-memory Channels is a fallback when REDIS_URL is absent, unsuitable
  for reliable multiworker signaling. Authentication correctly refuses a process-local
  cache when production sharing is required; it can therefore become unavailable
  under a missing Redis configuration rather than silently dropping protection.
* **Dependencies:** pinning and old audit snapshots do not establish absence of
  exploitable dependencies. Refresh Python and npm advisory scans, distinguish
  runtime/native from build-tool dependencies, and evaluate compatible upgrades.
  No package downgrade or dependency installation was performed by this audit.
* **Recovery readiness:** prior backup reports are historical. Backup schedules,
  restore verification, storage retention and incident response still require current
  evidence. This audit did not access live backups or rotate credentials.

Recommended work order: S01 first; then S02–S04 and the legacy-media condition;
then shared visibility/block fixes including S08; then administrator authentication,
resource limits, production mode and erasure; finally the filename sink and broader
browser/device acceptance. Apply fixes locally, reverse the reproduction assertions
into security acceptance tests, and obtain a clean security regression run before
any separately requested deployment.

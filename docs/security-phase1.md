# Phase 1 security hardening

Prepared locally on October 19, 2026. No deployment, Git push, production SQL,
production variable change, credential rotation, backup creation, or restore was
performed. Earlier dashboard and release-preparation changes are preserved.

## Changes

- Web/API login share normalized, HMAC-keyed IP/account counters. Registration,
  refresh, Google authentication/linking, and push registration also have limits.
  Production counters use the existing Redis connection through a separate cache
  alias. Missing shared counters or Redis errors fail closed with generic 503s;
  exceeding a budget returns 429 with Retry-After. No IPs, account identifiers,
  passwords or Redis exception details are included in counter keys/errors.
- Login rejects malformed payloads and oversized credentials before password
  verification. Existing Django web CSRF protection and DRF authentication remain.
- Call and user WebSockets revalidate JWT/session credentials, password changes,
  active account state and delivery permissions. A watchdog closes idle revoked
  sockets; inbound and outbound events are checked. Call participation is checked
  before delivery, preventing passive reception after removal. Frames are bounded
  to 64 KiB with a 60-message burst and 20/second refill budget.
- Native call, incoming-call and messaging sockets renew credentials in place
  before access-token expiry. Renewal can only keep the same user identity. The
  mobile client requires support in the **first server handshake** before sending
  renewal credentials, preventing an older relay server or a later peer frame
  from exposing them to other participants. Browser session sockets keep their
  existing authentication path.
- Post creation/update/deletion now uses current organization MANAGE_POSTS
  capabilities, including reduced, suspended and removed memberships. Old and new
  associations are checked, so detaching a workspace cannot bypass revocation.
  Talent associations must belong to the author; event associations require the
  organizer's permission and consistent organization. Personal posts, permitted
  team posts, text/photo/video composition and existing ownership checks remain.
- Web Push registration and delivery permit only supported browser-vendor HTTPS
  endpoints (FCM, Mozilla, Apple and Windows notification hosts). Credentials,
  unsafe ports, host lookalikes and non-public DNS answers are rejected. Delivery
  verifies TLS, ignores environment proxies, disables redirects and uses bounded
  connect/read timeouts. Existing unsafe subscription rows are skipped. Push error
  logs no longer include raw delivery exceptions or response bodies/device tokens.
- Hosted production rejects DEBUG=true and absent, weak or known-development
  SECRET_KEY values at startup. Local development remains supported. The existing
  production secret and JWT signing identity were not changed.
- Regression fixtures now model authenticated socket credentials and the actual
  applied account schema during historical migration tests. Learning/opportunity
  template assertions target their own forms instead of the global post composer.
  No production schema or migration was changed.

## Dependencies

| Package | Before | Prepared and installed locally |
| --- | --- | --- |
| Django | 6.0.7 | 6.0.9 |
| Django REST Framework | 3.17.1 | 3.17.2 |
| PyJWT | 2.13.0 | 2.15.0 |
| sqlparse | 0.5.5 | 0.6.0 |

The resolver accepted these versions and `uv pip check` reported all installed
packages compatible. The already-declared pywebpush 2.0.3 dependency was installed
locally to exercise delivery regressions. No framework-major migration, forced
npm downgrade or production package installation was performed.

After the updates, an OSV lookup of 46 pinned Python packages flags only the
Twisted IMAP advisory GHSA-8pqf-f4m5-798g. The reviewed application uses Daphne,
not an IMAP service. A clean version lookup does not prove runtime security or
cover every transitive/native dependency.

The Expo production dependency tree still has 19 high findings rooted in braces
and node-forge. The reviewed advisories list no patched release; retain an
exposure assessment and use reviewed upstream fixes when available. Do not force
an incompatible Expo downgrade to make the audit count disappear.

## Backup readiness: BLOCKED

Read-only checks at **2026-10-20 01:24 UTC** verified the expected Railway project,
production environment, application/database reference and Postgres volume:

| Check | Result |
| --- | --- |
| Railway volume backups | 0 |
| Backup schedules | 0 |
| PITR | Disabled |
| PITR archive wired | No |
| Successful restore rehearsal | Not verified |

`scripts/check_backup_readiness.py` repeats fixed metadata/status reads, withholds
sensitive CLI errors, and refuses to call a metadata check a verified restore.
It never creates/restores backups, enables networking, changes variables or runs
SQL. External/offsite backup arrangements were not available to verify.

Before approving any production rollout, an authorized operator must establish
and verify a recoverable backup, an automated schedule/retention policy, agreed
recovery objectives, and a restore rehearsal in an isolated approved environment.
PITR enablement and restore provisioning are separate production changes requiring
approval. Database snapshots do not establish Cloudinary/media backup coverage.

## Verification commands

```powershell
.venv\Scripts\python.exe -B scripts/test_security_phase1.py
.venv\Scripts\python.exe -B scripts/test_security_phase1.py --all --fast
.venv\Scripts\python.exe -B -m unittest scripts.test_backup_readiness
.venv\Scripts\python.exe -B scripts/check_backup_readiness.py
uv pip check --python .venv/Scripts/python.exe
```

The test runner forces an in-memory SQLite database, local cache/channel layer,
temporary media and non-delivery email/push configuration. Authentication limits
remain effective inside each test; their counters are isolated between fixtures.
`--fast` changes only fixture password hashing in this isolated process. Focused
authentication/socket regressions also run using the normal password hasher.

From `mobile/`, run `npm.cmd test` and `npm.cmd run typecheck`.

Verification results:

- Focused Django security/feature suite: **175 passed**, normal password hasher.
- Messaging realtime suite after fixture correction: **7 passed**.
- Production/media/authentication/post checks: **35 passed** in an earlier focused
  run (overlaps the focused suite; counts should not be added).
- Backup-checker unit tests: **5 passed**.
- Mobile suite: **90 passed, 2 browser-only tests skipped, 0 failures** (92 total).
- Mobile TypeScript check, Python syntax checks and `git diff --check`: passed.
- Installed Python dependency consistency: **68 packages compatible**.
- Full Django run: **951 tests; 934 passed, 16 skipped, 1 test-fixture error**.
  The run collected the earlier anonymous-socket fixture before its correction;
  it attempted to issue a JWT for AnonymousUser. That fixture is fixed, and all
  **7 messaging realtime tests subsequently passed**. The full suite was not
  repeated after that fixture-only correction. The final additional push identity
  regression is covered by the 175-test focused run.

SQLite/in-memory tests do not replace PostgreSQL concurrency and row-lock checks,
dedicated Redis integration tests, browser/device acceptance, or a recoverable
production backup. The full-run fixture error is documented above.

## Remaining risks and rollout conditions

- Backup readiness remains a release blocker. No production hardening is active
  until a separately approved deployment is completed.
- Private Cloudinary delivery restrictions and legacy public asset migration
  remain unverified/unresolved; application authorization cannot revoke an already
  public CDN URL. Review this before treating private attachments as protected.
- Existing incorrectly associated posts were not modified. Review legacy
  affiliations before an owner-approved data repair; new checks prevent new
  unauthorized associations and mutation after membership revocation.
- JWT logout currently clears device credentials without server-side refresh-token
  revocation/rotation. Password changes and expiry are enforced, but a stolen
  refresh token can remain usable until its expiry. This requires a separate
  session-lifecycle change and corresponding mobile/offline tests.
- Storage erasure after account deletion, contact-email minimization, comprehensive
  upload validation/scanning, filename DOM injection and CSP remain follow-up work.
- Native clients without renewal support will reach their access-token deadline
  on the hardened backend. Coordinate the compatible mobile build and backend
  rollout; do not deploy a backend change assuming every installed client is new.
- Physical-device/locked-screen/background tests, PostgreSQL concurrency behavior,
  TURN provisioning and public policy/operator completion still require acceptance.
- Authentication IP limits reuse the existing trusted-proxy configuration. Verify
  that the deployed proxy overwrites the configured client-IP header and that
  shared Redis counters work across workers before approving rollout.
- Web Push destinations are intentionally limited to the reviewed vendors. Add
  any new provider through reviewed code/tests, never a client-supplied allowlist.

References: [Django security release](https://www.djangoproject.com/weblog/2026/oct/06/security-releases/),
[DRF request-size fix](https://github.com/advisories/GHSA-2m8g-3cmr-wg3w),
[PyJWT releases](https://github.com/jpadilla/pyjwt/releases),
[Railway backups](https://docs.railway.com/volumes/backups),
[braces advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm),
[node-forge advisory](https://github.com/advisories/GHSA-86w9-cpqp-85rv).

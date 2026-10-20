# Security hardening Phase 2

Implemented locally; not deployed. No production database or data was accessed,
no Railway setting was changed, and no secret was rotated.

## Changes

- New uploads under feed, message, and learning private-media namespaces now use
  Cloudinary `authenticated` delivery. Private media URLs point to the app's
  ACL-checked `/media/` route. The route resolves the owning post, conversation,
  or lesson and checks the existing visibility, membership, or enrollment rule
  before streaming local or Cloudinary bytes. It supports range requests, keeps
  responses private/no-store, and sends file attachments with safe filenames.
  Public profile/portfolio media retains its existing public behavior.
- JWT access tokens issued with a refresh session carry that session's JTI. The
  new authenticated `/api/auth/logout/` endpoint blacklists only the caller's
  refresh token. API and WebSocket authentication reject access tokens for a
  blacklisted session; refresh rejects revoked or invalidated sessions. Mobile
  sign-out attempts server revocation before clearing local tokens and still
  clears local credentials if offline.
- Added focused media and logout regression tests. The JWT blacklist app uses
  SimpleJWT's built-in migrations; deployment would require applying migrations,
  but that was not done here.
- Added an isolated Railway backup/restore drill plan in
  `railway-postgres-backup-restore-plan-phase2.md`. It contains no live
  credentials or production connection instructions to execute now.

## Remaining dependency findings

The npm audit snapshot found 36 advisory entries in the mobile dependency graph:
26 high, 9 moderate, and 1 low. These are affected-package entries, with many
transitive duplicates. The key blockers include `braces@3.0.3` (pulled through
EAS/Expo tooling; no patched release is published) and `node-forge@1.4.0` (the
latest npm release when checked, but affected by a newer advisory). Expo 57 and
React Native 0.86 also receive high-severity audit findings; npm proposes
framework downgrades to Expo 44 / React Native 0.72, which are incompatible
major downgrades and were not applied. The audit's suggested EAS CLI downgrade
is likewise unsafe. `npm audit fix --dry-run` could not finish because the npm
advisory endpoint returned an error. No lockfile changes were made in Phase 2.

The pinned Python requirements pass `uv pip check` (68 packages). `pip-audit`
is not installed in this environment, so this verifies package consistency, not
the absence of known Python CVEs. A fresh complete Python advisory scan remains
open.

Sources: [braces advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm),
[node-forge advisory](https://github.com/advisories/GHSA-86w9-cpqp-85rv).

## Media and session limitations

Pre-existing Cloudinary objects were uploaded as public assets. The application
proxy enforces database ACLs for those paths now, but previously shared direct
Cloudinary URLs remain accessible until an authorized migration changes the
assets to authenticated delivery and verifies eager playback derivatives. That
migration has not been run. Access tokens issued before this change do not carry
a session JTI and remain valid until their normal expiry. Mobile server-side
revocation also requires connectivity; offline sign-out still clears the device.
Expired blacklist records should be removed periodically with SimpleJWT's
`flushexpiredtokens` management command.

## Backup readiness

The last metadata-only readiness report (Phase 1, 2026-10-20) recorded zero
volume backups, no schedule, PITR disabled, and no verified restore. Phase 2 did
not recheck production metadata. Recovery readiness therefore remains
unverified; follow the plan in an isolated target after the appropriate change
approval.

## Verification

- Isolated full Django suite: **959 tests run, 16 skipped**, no failures. It ran
  with in-memory SQLite and fixture-only local settings (`--all --fast`).
- Focused media and JWT logout tests: **19 passed**.
- Mobile test suite: **90 passed, 2 skipped**; TypeScript typecheck passed.
- `uv pip check`: all 68 installed Python packages are consistent.
- `git diff --check`: passed (Git emitted only existing LF-to-CRLF working-copy notices).

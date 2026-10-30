# Verification evidence and historical CDN remediation

This local change adds document authorization and an explicit historical-provider
migration tool. **Nothing was deployed. No live provider inventory, rename,
invalidation, application database update, or file deletion was performed.**
Historical CDN exposure is not resolved until the migration and operational CDN
checks have actually run in the intended environment.

Updated offline assessment: [historical Cloudinary exposure audit and CDN revocation procedure](cloudinary-exposure-audit-2026-10-28.md). It records namespace exceptions, signed/custom-domain verification gaps, safe batch/resume steps and acceptance gates. No production inventory or revocation was performed for that audit; even the command's default inventory requires provider access.

## Delivery policy

Verification evidence is delivered only through the application's `/media/` route.
An active document owner or current active platform ADMIN/superuser may download
a referenced document, including an approved or rejected request. Staff flags and
organization capabilities alone do not grant this access. Reviewer authority and
account activity are checked against the database, including stale request users.
Unreferenced paths return 404 even to reviewers; physical bytes are not deleted.
Blocks and talent profile visibility do not prevent authorized verification review.

The same checks cover session and JWT requests, GET, HEAD and byte ranges, before
local or provider reads. Downloads are attachments with no-store, nosniff, sandbox
and no-referrer headers. Signed provider URLs stay server-side. Verification pages
are not cacheable, and Django admin model permissions alone cannot authorize a
nonreviewer to manage evidence. Existing legitimate administrators are preserved.
There is no new mobile verification workflow: mobile JWT delivery uses this route.

New verification uploads already start with Cloudinary's `authenticated` delivery
type. That protects originals and derivatives; `private` protects originals only.
See [Cloudinary access controls](https://cloudinary.com/documentation/control_access_to_media).
Local production servers must route `/media/` through Django rather than serve
MEDIA_ROOT directly. Private files must not be copied into a public static bucket.

## Historical migration

`privatize_media` is a maintenance command, never a startup/deploy hook. It uses
the configured Cloudinary account and storage prefix. Without `--apply` it only
inventories provider metadata and writes a local manifest. The cloud name must
be explicitly supplied and match configuration before any provider request.

The default inventory includes all configured private namespaces: verification,
portfolio, private feed/message storage, lessons and certificates. Subsequent
profile/event hardening also added canonical talent and legacy athlete photos/media,
achievements/certifications, event images and galleries. General account identity
photos, organization logos and course thumbnails are excluded. A `--prefix` argument can limit
the initial plan, e.g. `verification_documents/`. Inventory includes orphaned files,
all image/raw/video resources, paginated results, and both legacy `upload` and
`private` delivery types. Existing authenticated files do not need moving.

Review a new inventory for newly added namespaces; keep existing journals intact.
Public profile/event delivery remains available through the app's owning-record
ACL even when provider storage becomes authenticated. See the
[profile/event policy](profile-event-privacy-fix.md).

The plan records public ID, resource type, immutable asset ID, byte count and ETag.
Missing identity/checksum metadata requires manual investigation. It stops on
duplicate destinations, unexpected namespaces or environment mismatches.

Apply rechecks source identity and refuses an existing authenticated destination.
It changes delivery type **in place**, keeps the public ID, passes
`overwrite=False, invalidate=True`, then verifies identity/size/checksum and confirms
the old source no longer exists at origin. Database references and file bytes stay
unchanged. It does not re-upload, overwrite, delete originals or roll back to public.
See [Cloudinary rename semantics](https://cloudinary.com/documentation/rename_assets).

Each mutation has an atomic, flushed manifest checkpoint before and after it.
A lost successful provider response can be resumed after validating the exact
authenticated identity. A mismatch stops the run for investigation; it never
silently accepts a different file. Provider exceptions are not printed with signed
URLs. An exclusive manifest lock prevents concurrent runs on that manifest.

Example for an operator in the intended environment, after reviewing this change
and provisioning a restricted `.audit-private-media/` directory:

```powershell
# Read-only provider inventory; no asset changes.
.venv\Scripts\python.exe manage.py privatize_media --cloud-name YOUR_CLOUD --manifest .audit-private-media/plan.json

# Changes provider delivery types, at most 100 files per invocation.
.venv\Scripts\python.exe manage.py privatize_media --cloud-name YOUR_CLOUD --manifest .audit-private-media/plan.json --apply --limit 100
```

Review the manifest before apply. Repeat the same apply command to resume remaining
files. Do not regenerate or hand-edit an in-progress manifest. Keep manifests and
known URL lists outside source control and restrict their filesystem access; IDs
and evidence URLs can be sensitive. `.audit-*/` directories are already ignored.
POSIX files are created with mode 0600; Windows operators must use an appropriate
directory ACL. Back up the journal securely. If a crash leaves a `.lock`, confirm
the prior process is no longer active and investigate its last checkpoint before
manually removing that lock. Never run multiple manifests over the same assets.

Use a controlled maintenance window so unrelated provider processes do not replace
source assets during migration. Admin API rate limits can interrupt inventory;
retry a fresh read-only plan if no manifest was written. Apply stops on errors and
retains its journal. Names outside the configured prefix, historical custom CDN
domains and dynamic-folder IDs outside these namespaces need a separately reviewed
inventory. The tool does not guess their ownership. For video/audio, also verify
existing eager playback variants remain available through the application proxy.

## CDN revocation verification

The journal deliberately labels success `origin_private_cdn_pending`, not revoked.
Invalidation propagation is asynchronous, and versioned/unversioned URLs with
folder paths can depend on provider invalidation settings. Review those settings
and obtain provider support for unsupported variants. Do not announce remediation
complete solely because the rename returned successfully. See
[Cloudinary cache invalidation](https://cloudinary.com/documentation/invalidate_cached_media_assets_on_the_cdn).

Put known exposed URLs in a restricted JSON array file, including original,
versioned and transformed variants. After migration, an optional read-only check
revalidates private origin identity and requests those exact URLs without login:

```powershell
.venv\Scripts\python.exe manage.py privatize_media --cloud-name YOUR_CLOUD --manifest .audit-private-media/plan.json --verify-urls .audit-private-media/exposed-urls.json
```

Only HTTPS `res.cloudinary.com` URLs for the same cloud and migrated assets are
accepted. It validates the whole list before network access, never follows redirects,
never sends application/provider credentials, streams a one-byte range and closes
responses. It records observed status codes and timestamps in the manifest.
200/206 responses mean exposure remains; redirects, server errors and network
failures are inconclusive. 401/403/404 indicate denial at that network location.
Recheck from relevant regions after propagation and confirm provider invalidation
coverage for every known URL variant. A fresh inventory should show no legacy
assets remaining in scope. No application change can recall copies already saved
by a previously authorized viewer or third-party/browser caches.

## Tests

Tests use temporary storage, an isolated database and mocked Cloudinary/HTTP
transports. They cover owner/reviewer/outsider access, stale revoked reviewers,
inactive accounts, orphan files, JWT, HEAD/Range, safe download headers, admin
permissions, provider access order, preservation across every private namespace,
pagination, collisions, checksum mismatches, checkpoint failures, lost responses,
bounded resumable execution and CDN checks/SSRF restrictions.

Validation completed: 136 backend tests, 135 passed and one skipped. Whitespace
checks passed, and the migration drift check reported no changes. No live provider
or physical-device validation was performed.

```powershell
.venv\Scripts\python.exe -u -B scripts/test_security_phase1.py config.test_private_media_migration talents.test_verification_security config.test_upload_security config.test_media dashboard portfolio accounts.test_role_security --fast
```

# Upload and file delivery hardening

Implemented locally; not deployed. Existing stored files, database names and
records are not rewritten or deleted. No Cloudinary asset migration was run.

## Upload validation

`config/upload_security.py` defines a shared file policy. A multipart upload handler
enforces it for web forms and REST POST/PUT/PATCH requests, before persistence.
The production local and Cloudinary storage backends also validate new writes.
Invalid uploads return a controlled 400 response with a safe message and field
errors; storage policy failures do not become unhandled server errors. CSRF and
normal authentication/object permissions remain in force.

Allowed extensions must match supported byte signatures. A supplied MIME header
is not treated as proof of file type. HTML, SVG, XML, JavaScript and executable
extensions are not accepted as new uploads. Renaming HTML to MP4/JPEG/MP3/PDF does
not pass the signature checks. Raster images, common camera/video containers,
Safari MP4/M4A, Chrome WebM, Firefox Ogg, PDFs, text and common office/archive
documents are supported. Text documents containing markup remain valid documents
and are delivered as downloads.

These are bounded container/type checks, not antivirus scanning or a guarantee
that a file is harmless when a user opens it in an external application. The
delivery policy is the second protection against browser execution, including
polyglots and old files that were uploaded before validation existed.

Defaults are 20 MiB for images, 50 MiB for audio, 200 MiB for video/gallery media,
25 MiB for documents, and 250 MiB of combined file bytes per request. Counters use
actual received bytes rather than trusting Content-Length. `AWINLINK_UPLOAD_LIMITS`
(per-kind values in bytes) and `AWINLINK_UPLOAD_TOTAL_BYTES` can configure these
limits. They do not retroactively reject or alter stored files.

## Delivery

All application `/media/` URLs, in DEBUG and production, use the same checked
delivery view. The raw Django static-media fallback was removed. Known public
media namespaces remain public; private posts/messages/lessons retain object
authorization. Lesson creators and platform reviewers can access their authorized
lesson media. Verification documents require their owner or an authorized
administrator; stored certificates require their enrollment owner. Internal
playback-cache paths and traversal/unknown paths are not public routes.

Only an explicit raster/audio/video MIME allowlist can render inline. HTML, SVG,
XML, unknown media and document originals are served as `application/octet-stream`
with attachment disposition. Responses include `nosniff`, a sandbox CSP,
no-referrer and private/no-store headers. Cloudinary HTML/SVG MIME headers and
disposition headers cannot make the app forward an active document inline.
HEAD and range responses retain safe delivery rules. Attachment filenames use
Django's encoded disposition helper, with control characters removed.

Existing originals remain available through safe downloads; no blanket cleanup or
conversion replaces uploaded bytes. On-demand audio/video playback still produces
separate cached derivatives. Existing local and Cloudinary paths remain usable.
Legacy Cloudinary documents previously placed in the image namespace have a bounded
fallback when the raw namespace returns 404; extensionless gallery media can also
fall back to video delivery. Internal storage reads/size/exists use provider URLs,
not the public app URL, so certificate/document reads continue working.

New raw Cloudinary documents request attachment delivery. Verification documents
and certificates join the authenticated-upload prefixes. Public application URLs
for Cloudinary media now point through `/media/`, including profile images, so the
application controls its delivery headers consistently.

## Web and mobile

Web attachment previews now use textContent rather than interpreting selected
filenames as HTML. Filename line breaks remain visible.

Mobile/web API responses resolve relative media fields to the API origin. Account
credentials are sent only to that origin's `/media/` routes, and untrusted media
URLs cannot use JavaScript, data or credential-bearing schemes. Local recordings
use a separate explicit preview option so device-created file/blob recordings
still play without sending credentials.

File/lesson-note/certificate downloads fetch bytes with authorization instead of
discarding JWT headers in an external-browser navigation. Web exports use inert
download blobs; native exports use temporary files and the platform share/save
flow, cleaning temporary bytes on completion/failure. Legacy active filenames get
a `.download` suffix during export. Android exports above 50 MiB report a device
export limit rather than loading excessive base64 data into the app; originals
and streaming playback are unchanged. Original-file exports remove the app's
playback conversion query and assign safe extensions to opaque cloud media IDs;
trusted local recording exports copy rather than delete the recording. Upload
preflight rejects obvious active
filenames on web/native, with the server remaining authoritative. Course thumbnail
uploads use the real browser File on web.

## Preservation and remaining boundary

There is no data migration, automatic deletion, batch rename, administrator reset,
or course/roster change. Two older test fixtures now reuse the seeded Arts/Sports
course categories instead of attempting duplicate inserts; this changes no
application data.

Already shared direct Cloudinary URLs are outside the application's response-header
boundary. Existing public assets may still be reachable at those provider URLs
until a separately authorized inventory/migration changes provider delivery.
This work does not claim to revoke those historical URLs or to fix unrelated
profile visibility findings. Public media proxying also adds application traffic;
evaluate release capacity before deployment.

## Validation

`config/test_upload_security.py` covers type spoofing, active extensions, size
limits, POST/PUT/PATCH parsing, storage guards, legacy downloads, permissions,
range/HEAD responses, cloud MIME handling/fallbacks, and preservation of original
bytes. Existing media tests include real FFmpeg audio/video conversion and seeks.
`mobile/tests/upload-security.test.cjs` covers URL boundaries, web/native preflight,
authenticated downloads and cleanup, inert blob downloads, relative URLs, and
the filename preview sink.

Tests use isolated SQLite databases, temporary files, and mocked Cloudinary
transports. No production database or real uploaded asset is used. Device share
dialogs and live CDN/provider behavior were not exercised.

Run locally:

```powershell
.venv\Scripts\python.exe -u -B scripts/test_security_phase1.py config.test_upload_security config.test_media feed.test_post_composer learning.test_mobile_lessons learning.test_classroom_models --fast
.venv\Scripts\python.exe -u -B scripts/test_security_phase1.py --all --fast
.venv\Scripts\python.exe -B manage.py makemigrations --check --dry-run --settings=config.rising_talent_test_settings
```

From `mobile/`, run `npm.cmd test` and `npx.cmd tsc --noEmit`.

Subsequent portfolio authorization remediation also protects portfolio media paths
and makes new portfolio provider uploads authenticated. See
[portfolio authorization remediation](portfolio-authorization-fix.md); the results
below describe the earlier upload hardening verification.

Historical sensitive CDN assets now have a separate journaled maintenance command
with invalidation and known-URL checks. It has not been run against live assets.
See [verification and historical CDN remediation](verification-private-media.md).

Validation results:

* Full Django regression run: **1,236 tests, 63 skipped**, no failures.
* Focused upload/media/classroom verification: **68 tests passed**, including the
  additional transfer-encoding regression that prevents corrupt download lengths.
* Mobile full run: **151 tests, 148 passed and 3 browser-only skips**.
* Focused mobile upload/media checks: **11 passed**.
* TypeScript and whitespace checks passed. Migration drift check reported
  **no changes detected**; this fix adds no migration.

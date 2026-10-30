# Historical Cloudinary exposure audit and revocation procedure

Date: 2026-10-28. **Historical exposure and CDN revocation remain unverified.** This is an offline source audit and a prepared procedure, not evidence that production assets are currently public or remediated. No production account, database, asset URL, logs, credentials or provider inventory was accessed. No files/assets were deleted, renamed, uploaded or invalidated. Nothing was deployed. Only public vendor documentation was browsed.

“CN revocation” is interpreted here as CDN revocation, including any custom CNAME/CDN domains. No certificate or credential revocation was performed.

## Findings and blockers

| Priority | Source finding | Implication / evidence needed |
| --- | --- | --- |
| High | App ACLs and new authenticated uploads do not revoke historically distributed provider URLs. Prior reports contain no completed live inventory, migration or multi-location CDN verification. | Historical sensitive originals/derivatives may remain reachable independently of app login. Asset population, recipients, dates and actual access are unknown; do not claim an observed production breach or successful revocation. |
| High | The migration inventories only configured private public-ID prefixes, current cloud/prefix, image/raw/video resources and upload/private delivery types. Already-authenticated assets are skipped. | Old prefixes/clouds, dynamic-folder IDs, custom domains, copies, signed URLs and independently generated derivatives need separate reviewed coverage. An empty scoped inventory is not proof of no exposure. |
| High, conditional | `coaches/profiles/` and `coaches/covers/` are actual CoachProfile upload namespaces, excluded from PRIVATE_PREFIXES and explicitly allowed by the app's public media fallback without an owning-record lookup. | Do not silently treat every profile photo as private. Obtain an explicit policy decision for these namespaces, including blocked/inactive/hidden cases. If their policy requires restricted access, ACL/storage migration work is a blocker before claiming complete profile-media protection. This audit does not change that policy or runtime behavior. |
| High | A successful rename requests invalidation but leaves journal state `origin_private_cdn_pending`. | Origin privacy is not edge revocation. Verify the account's invalidation coverage and every known exposure variant; signed/custom-domain routes need separate handling. |
| Medium | The built-in checker allows only this cloud's res.cloudinary.com URLs matching migrated manifest records. It does not reject query strings or signed-path components, and does not establish a previously working baseline. | Restrict its input to reviewed unsigned, credential-free, historically valid URLs. Do not feed tokenized/signed links into a broadly shared manifest or interpret arbitrary 404s as proof of revocation. |
| Medium | The proxy uses server-side signed authenticated URLs and retains an upload fallback after 404; its upstream request allows redirects. | App denial and origin revocation must be tested separately. Review upstream trust/redirect handling and confirm signatures never escape into responses/logs. Fallback compatibility does not make a legacy public asset private. |
| Medium | Video/audio playback may require existing eager derivatives; migration itself does not generate missing playback variants. | Prove authorized playback in a separate test cloud before a live batch. Learning/video and legacy variant coverage must not be inferred from the message/feed eager-upload settings. Do not reopen public delivery to fix a playback failure. |

## Current source controls and coverage

`config/media_storage.py` uploads configured private namespaces with delivery type authenticated. The public ID/name is preserved. `config/media_views.py` checks app owning-record permissions before delivery; `url()` for these namespaces uses the app media route, while authenticated provider signatures are generated server-side. Public record visibility may still permit app delivery: authenticated storage is not equivalent to an owner-only product policy.

| Asset class | Private migration scope / app policy |
| --- | --- |
| Verification documents | verification_documents; document owner/current authorized reviewer, including current account checks. |
| Messages and group images | messages/groups, images, files, audio, videos; conversation membership. |
| Feed / portfolio | feed images/videos and portfolio images/files; existing post/item permissions. |
| Lessons / certificates | learning videos/notes and certificates; configured creator/admin/enrollment or certificate-owner rules. |
| Talent / legacy athlete / achievement / certification | talent/athlete profile, cover and media paths plus achievements/certifications; applicable owning-record visibility. |
| Events | event images/gallery; event state and organization/history access rules. |
| Excluded public-policy namespaces | Account profiles, organization logos/covers, coach profiles/covers, learning thumbnails and sports icons. Do not migrate these automatically under a private-prefix claim. |

This table describes code paths, not a fresh audit of every ACL's correctness or deployed configuration. Orphan files within the configured prefixes are included in provider inventory; app denial of an orphan does not remove its CDN copy. See [verification delivery policy](verification-private-media.md), [profile/event policy](profile-event-privacy-fix.md), and [retention/erasure policy](media-retention-30-day.md).

Cloudinary documents different original/derivative protections for private and authenticated delivery, and signed URLs as an access mechanism. Random IDs and noindex do not establish access control. Verify delivery behavior with fixtures, rather than assuming private originals imply private transformations. [Provider access controls](https://cloudinary.com/documentation/control_access_to_media).

## Prepared migration procedure — not executed

All account access, real inventory and provider mutations below require separate explicit authorization. Even `privatize_media` without --apply contacts the configured provider; it is not an offline dry run. Do not run it under this task's no-production-access boundary.

### 1. Scope and evidence

- Identify the intended environment, database reference, cloud and prefix through an authorized operator. The tool's cloud/prefix comparison alone does not distinguish environments sharing those settings. Keep actual credentials and raw asset URLs in restricted systems.
- Inventory file references from an approved restored copy and provider metadata through a separately approved read route. Record cloud, immutable asset_id, public_id, resource type, delivery type, size, ETag, versions and known derivative identities. Distinguish referenced, shared, orphaned and legally held assets; orphaned does not mean deletable.
- Account for older upload presets, namespaces, cloud accounts, dynamic-folder layouts, copied assets and custom CDN hosts. Do not infer folder ownership from a UI folder label or guess a public ID. Build a reviewed list of known previously distributed URL variants without scanning or brute-forcing IDs.
- Record prior exposure evidence if available: affected classes/time window, distribution route, whether a URL was unsigned or bearer-signed, and confidence. A potential exposure is not evidence of access/download. Security/privacy owners determine any incident response separately.
- Obtain recoverable metadata/journal backups and reviewed byte-preservation evidence, retention/hold decisions and dependency owners. A PostgreSQL backup does not contain Cloudinary media. Preserve originals and database references throughout this procedure.

### 2. Rehearse separately

Use a separately identified test cloud with synthetic assets, isolated DB/configuration, fake recipients and no production provider access. Exercise image/raw/video, both legacy source types, shared references, orphans and transformed/versioned playback. Check the same immutable identity and bytes before/after migration; verify app owner access, outsider denial and public-record behavior where intended.

Confirm that the provider preserves the identity/size/ETag required by the tool for each supported resource class. Unsupported semantics or absent checksum/identity are stop conditions, not reasons to relax matching. Verify eager playback availability for authenticated delivery. A test-cloud success still needs a reviewed production plan.

### 3. Plan a bounded batch

The existing `talents/management/commands/privatize_media.py` command can inventory a selected PRIVATE_PREFIXES subset into a new manifest. It enumerates upload/private metadata with pagination and includes orphans. Inventory must be complete before a manifest is accepted; rate-limit failures are not a clean result.

Review collisions, unmatched references and out-of-scope identities before apply. Secure the manifest directory with appropriate Windows ACLs; POSIX mode 0600 alone does not configure Windows ACLs. Preserve restricted copies of journals and URL evidence outside Git and shared logs. Arrange one operator/migrator and quiesce provider jobs that could overwrite or move these assets. A per-manifest lock does not prevent two different manifests from targeting the same asset.

Future operator command shapes, deliberately not executed here:

```text
python manage.py privatize_media --cloud-name REVIEWED_CLOUD --manifest RESTRICTED_NEW_PLAN --prefix verification_documents/
python manage.py privatize_media --cloud-name REVIEWED_CLOUD --manifest REVIEWED_PLAN --apply --limit 1
```

Start with one reviewed canary and prove access/identity before increasing a batch. Never edit an in-progress journal or regenerate it to hide a failure. The existing command creates/removes its own temporary journal/lock files during execution; it was not invoked during this no-file-deletion audit.

### 4. Apply and recover safely

The tool checkpoints before and after a same-public-ID rename to authenticated with overwrite=False and invalidate=True. It verifies immutable identity, size/ETag and absence of the old origin. It does not re-upload bytes or update database references. Provider rename/invalidation is a mutation even though it is not file deletion. [Rename semantics](https://cloudinary.com/documentation/rename_assets).

On failure, stop the batch and preserve the journal:

| Observed state | Safe next action |
| --- | --- |
| Source matches, no destination, checkpoint planned | Review cause; resume only the same journal after confirmation. |
| Moving checkpoint, response lost; source absent and exact authenticated identity present | The tool can resume after identity validation without repeating the rename. |
| Source/destination mismatch, both exist, checksum absent/changed, unexpected namespace or identity | Stop for investigation. Never overwrite, merge, delete either object or relax comparison to force completion. |
| App playback fails after origin migration | Keep the asset private, pause migration, inspect authenticated derivative/access behavior in isolation. Do not roll back to upload/private/public delivery. |
| Stale lock | Establish prior process termination and last completed checkpoint. Preserve evidence; lock recovery is a separately authorized filesystem action, not an instruction to delete files now. |

Do not run uploader.destroy/delete_resources, implicit storage deletion, erase_ready_media_jobs apply, bulk cleanup or orphan deletion as remediation. Retention, legal holds and erasure are separate processes. Do not reverse delivery type to public as a rollback.

## CDN revocation procedure — separate from migration

Cloudinary's invalidation coverage depends on URL form and account configuration. Signed URLs are not invalidated by default and may require provider support. Nested public IDs, versioned routes and custom CDN behavior need explicit coverage confirmation. Cache-busting a new URL does not revoke an old URL. [Invalidation rules](https://cloudinary.com/documentation/invalidate_cached_media_assets_on_the_cdn).

1. Preserve known exposed originals, unversioned, /v1/, explicit historical versions, formats, transformations, eager video/audio variants, manifests/segments where used, custom CNAME/CDN routes and any known signed/tokenized links in separate restricted evidence. Do not publish a URL list or generate speculative transformations against production.
2. Have the provider/account operator confirm invalidation coverage and request the necessary scoped support action for unsupported variants, particularly signed/custom-host paths. Capture a sanitized support/evidence reference, affected asset identity, requested scope and UTC time. No support message or invalidation request was sent in this audit.
3. Retain `origin_private_cdn_pending` until verification and owner sign-off. Origin API lookup must show the old delivery identity absent and the exact authenticated asset retained. Invalidation acknowledgement alone is insufficient.
4. Verify exact known URLs anonymously from relevant approved network locations, without cookies, Authorization, proxy credentials or redirects. Use bounded, streamed requests, close responses and avoid collecting response bodies. Do not append cache-busting parameters to the only check: that may test a different cache key.
5. Keep each location/time/variant observation separately; the command stores only last_url_check and can overwrite previous observations. If a network exception interrupts the list, complete evidence may not have been saved. Preserve prior journal snapshots, mark the attempted run inconclusive and recheck under the approved plan.
6. Re-inventory every reviewed legacy scope after propagation, separately reconcile already-authenticated, custom-domain and out-of-prefix assets, and verify authorized application access still works. Signed/tokenized exposure needs a dedicated reviewed access-expiry/revocation approach; do not assume rotating an API credential or changing an application URL revokes every old delivery URL.

The optional --verify-urls command contacts provider metadata and exact CDN URLs and writes the journal. It only accepts res.cloudinary.com for the configured cloud, matching migrated upload/private manifest records; it cannot establish custom-domain coverage or global revocation. Use only reviewed unsigned, credential-free known URLs with this checker. Handle leaked bearer URLs separately as secrets. A clean checker result is a limited observation, not incident closure.

| Observation | Interpretation |
| --- | --- |
| 200 or 206 on a known restricted unsigned legacy URL | Exposure remains at that route/location; fail the revocation gate. |
| 401/403/404 on a previously working exact URL | Denial observed there at that time. Cross-check correct identity and rule out typo, unsupported transformation or transient WAF behavior. Not proof of global purge. |
| Redirect, 429, 5xx, timeout, DNS/TLS failure or incomplete list | Inconclusive; do not follow arbitrary redirects or classify this as revoked. |
| HEAD denies but GET/Range serves | Exposure remains. HEAD-only verification is insufficient. |
| Origin private, known edge URL serves | CDN pending/failed; preserve origin privacy and escalate invalidation coverage. |

## Acceptance checklist

- [ ] Approved cloud/environment/scope and public-vs-private policy, including coach/public exceptions.
- [ ] Authoritative asset/URL inventory and coverage for old prefixes, copies, custom hosts, signed URLs and derivatives; unknown scopes remain explicit blockers.
- [ ] Exact immutable identity/bytes preserved; database references/history unchanged; no deletion or overwrites.
- [ ] Anonymous/outsider/removed-member app requests denied where required; legitimate owners/reviewers/public viewers retain intended access. Exercise session/JWT, GET/HEAD/Range, private/no-store and safe headers; check signatures/credentials do not appear in responses/logs.
- [ ] Authenticated image/raw/video and required eager playback proven; source origin identities absent.
- [ ] Provider invalidation scope confirmed; exact historical URLs denied from the approved locations after propagation, with no unknown/accessible variants silently waived.
- [ ] Privacy/security owner records the limits of cache evidence, previously downloaded copies and any further incident action. Files already saved by recipients cannot be recalled by CDN invalidation.
- [ ] Backup/restore and erasure procedures will not republish historical assets or undo later holds/revocations. Journal and evidence retention owners named; no file deletion is authorized by this checklist.

## Offline validation in this audit

**14 pure migration/verifier tests passed**, using in-memory fake provider assets and mocked HTTP responses. Tests covered identity/byte preservation, all configured private prefixes, destination collisions, checkpoint failure, lost-response recovery, inventory pagination/scope/checksum failures, exact CDN status handling and URL restrictions. Environment application secrets were stripped, dotenv loading disabled, outbound socket connections blocked, and Python bytecode writes disabled. No management command, real provider call, application database, temporary-file test or deletion workflow ran.

The first minimal fixture import lacked the SDK's required dummy credential fields; supplying synthetic fixture values resolved that setup issue. No real credentials were read. Historical broader ACL tests are recorded in [migration safety validation](migration-safety-fixes-2026-10-28.md); they were not rerun here because this task changed documentation only. Actual provider rename semantics, edge denial, environment inventory and playback remain unverified production gates.

Local sources reviewed: config/media_storage.py, config/media_views.py, config/private_media_migration.py, talents/management/commands/privatize_media.py, config/test_private_media_migration.py, model upload paths and the linked policy reports. Changes in this task are this report and cross-references in existing documentation; runtime behavior is unchanged.

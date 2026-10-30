# Portfolio authorization remediation

S03 is fixed in the local working tree. No deployment or application data migration
was performed. Existing portfolio records, courses and uploaded files are preserved.

Portfolio lists, item details, web profiles and image/file delivery now use the
talent profile visibility policy. A missing or inaccessible item returns 404.
Inaccessible empty portfolios also return 404, rather than revealing the parent.

| Visibility | Authorized readers |
| --- | --- |
| PRIVATE | Active profile owner |
| ORGANIZATIONS | Owner and active users with a current organization VIEW_TALENTS capability |
| PUBLIC | Active unblocked users; anonymous media requests may read public assets |

API endpoints still require authentication. Bidirectional user blocks override
public and organization access. Inactive owners or viewers are excluded. A role
label, staff flag or superuser flag does not grant private portfolio access.
Organization membership and organization status are checked at request time.

Creating, updating and deleting require an active ATHLETE account and ownership.
Organization read permission never grants edit permission. Web and API mutations
reject ownership fields rather than accepting a different talent, user or owner.
Existing CSRF enforcement remains in place. Owner profile reads remain possible
after a role change; portfolio management requires the talent role.

Portfolio API responses, web profiles, management pages and media responses use
private/no-store caching. File authorization precedes local or provider reads,
including HEAD and Range requests. Unreferenced portfolio paths return 404 without
deleting the file. New Cloudinary portfolio uploads use authenticated storage.
Legacy files remain accessible through the authorized application proxy.

Historical direct public provider/CDN URLs remain outside application authorization.
Revoking those URLs requires an explicitly authorized provider migration and cache
invalidation. This change neither deletes nor silently migrates existing assets.
The subsequent [historical media migration tool](verification-private-media.md)
can migrate these files in place; no live provider migration has been executed.

Mobile native and web screens hide previous account/profile data immediately,
clear denied responses and discard late requests. Portfolio images use JWT headers
on native and authenticated fetch/blob URLs on web; temporary URLs are revoked on
cleanup. This does not withdraw files a previously authorized viewer already saved.

Validation uses isolated databases, temporary files and mocked provider requests:

* Backend affected-app regression run: 216 tests, one skipped, no failures.
* Portfolio/media/upload focused run: 72 tests passed.
* Mobile privacy/image regressions: 12 tests passed.
* Full mobile suite: 163 tests, 160 passed and three browser-only skips.
* TypeScript and whitespace checks passed; migration check found no changes.

Regression coverage includes all talent categories and viewer roles, organization
capability revocation, both block directions, owner-only writes, forged ownership,
inactive accounts, JWT media, HEAD/Range, provider authorization order, and mobile
account/profile request races. Physical devices and live CDN behavior were not tested.

Run `scripts/test_security_phase1.py portfolio config.test_media
config.test_upload_security --fast` with the workspace Python, and run `npm.cmd test`
and `npx.cmd tsc --noEmit` from `mobile/`.

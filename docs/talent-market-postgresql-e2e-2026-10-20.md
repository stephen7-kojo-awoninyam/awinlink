# Talent Market PostgreSQL validation — 2026-10-20

Tested locally on the workspace PostgreSQL 17.11 cluster, bound to loopback port 55432. All fixtures were synthetic. Django used `test_awinlink_audit_market_e2e_20261020`; no deployed or ordinary application database was inspected or modified. No deployment occurred.

## Results

30 tests passed, with no skips across the two successful runs:

| Coverage | Passed |
| --- | ---: |
| Existing API, discovery, consent, message history and permission regressions | 20 |
| Real loopback HTTP workflows, actual login and JWT authentication | 2 |
| Historical 0001 -> 0002 migration and preflight regressions | 3 |
| PostgreSQL concurrent offers, competing decisions and message/decision races | 4 |
| Real headless Chrome controls, session authentication and CSRF | 1 |

The 29 API/HTTP/migration/concurrency tests passed together. The browser test passed separately against the same isolated test database. Its first sandboxed attempt could not connect to Chrome DevTools; the rerun with the required local process/network access passed.

HTTP workflows covered draft creation, explicit-consent publication, discovery with Unicode filters, invalid domain filters, denied edits, personal and organization offers, duplicate prevention, exact acceptance consent, forged message authors, two-way Unicode messages, history pagination, final read-only rooms, immutable decisions, recruiter revocation, unauthorized organization teammates/admins, and blocks. Existing API tests also covered disabled accounts and organizations.

Chrome exercised `/marketplace/` with separate talent, scout and outsider sessions: create/publish a listing, send an offer, send and read messages, load older history, accept exact terms, hide unavailable controls, and reject unauthorized/final-room writes. Additional history was inserted through real HTTP message requests. External HTTPS resources were blocked in this local browser run. Physical Android/iOS apps and device rendering were not tested.

## Migration 0002 legacy-data audit

`0002_workflow_guards` is unchanged. It adds six database guards and performs no data repair:

| Guard | Legacy rows that block upgrade |
| --- | --- |
| `market_listing_valid_status` | Listing status outside DRAFT/PUBLISHED/PAUSED |
| `market_listing_publication_consent` | PUBLISHED listing without publication consent timestamp |
| `market_pending_personal_offer` | Multiple PENDING offers for one listing and personal sender |
| `market_pending_org_offer` | Multiple PENDING offers for one listing and organization, regardless of recruiter |
| `market_offer_valid_status` | Offer status outside PENDING/ACCEPTED/DECLINED/WITHDRAWN |
| `market_offer_decision_consent` | Inconsistent status, decision timestamp or talent consent timestamp |

Valid pending, accepted, declined and withdrawn offers upgraded with all original listing values, exact terms, messages, IDs and timestamps preserved. Each guard was tested individually against a seeded violation. Each failed migration rolled back, did not record 0002 as applied, and left all seeded data unchanged. These cases also proved earlier-added constraints roll back when a later operation fails. A combined dirty fixture tested the preflight report across all six guards.

The safe operational fix is `python manage.py audit_marketplace_legacy --database default`. It performs only reads, uses a repeatable-read/read-only transaction on PostgreSQL, reports counts plus at most 20 IDs/groups per guard, and exits nonzero when blocked. Duplicate counts represent groups. Both clean and dirty historical fixtures tested the command.

Before any future upgrade: back up, pause market writes, run preflight, review flagged records with their owners, resolve through explicitly authorized changes, and rerun preflight immediately before migrating. Never fabricate consent, silently select a duplicate winner, or delete deal history. The tests do not establish whether any deployed legacy database is clean.

## Reproduction

From the workspace PowerShell, with the dedicated local cluster running:

```powershell
$env:AWINLINK_AUDIT_POSTGRES_URL='postgresql://vc_audit@127.0.0.1:55432/awinlink_audit_market_e2e_20261020'
$env:TALENT_MARKET_TEST_CHROME='C:/Program Files/Google/Chrome/Application/chrome.exe'
.venv\Scripts\python.exe -u -B scripts/vc_audit.py test marketplace --noinput --verbosity 2
```

The test runner defaults to SQLite unless the explicit audit URL is set. That URL must name an `awinlink_audit_...` database on loopback. The browser test requires an installed Chrome executable and permission to reach its local DevTools port.

Rising Talent job audit — 2026-10-22
==================================

Scope: detection jobs, duplicate alerts, consent/organization privacy, evidence
reads, memory bounds, retention, query growth and overlapping workers. All job
executions used synthetic records in isolated test databases. No deployment,
scheduler change or application database migration was performed.

Findings corrected
------------------

1. **Repeated whole-catalog work.** Planning called the recommender separately for
   each recipient. Each alert creation and two delivery checks recomputed the
   entire top-50 ranking and scanned the skill catalog again. Candidate groups
   now share a topic-to-recipient index and one assessment per candidate within
   a bounded recipient group. Single-candidate creation/delivery checks no longer
   scan unrelated talents or the skill catalog. Static normalization aliases
   are compiled once; no profile/activity strings enter a process-wide cache.

2. **Already-alerted candidates starved new matches.** Choosing the top five
   before applying weekly receipts meant subsequent days kept selecting the
   same five and never reached other eligible talents. Weekly receipts are now
   excluded before bounded heap selection. Daily remaining capacity is applied
   before scoring, and exhausted recipients do not trigger evidence reads.

3. **Snapshot queries grew per talent and could retain stale observations.**
   Source skills were prefetched before waiting on consent locks, then each
   source did an eligibility query and get-or-create. The job now finds missing
   daily observations using keyset pages, acquires ordered consent locks, reads
   fresh eligible skills after those locks and bulk-inserts the group. Repeated
   runs skip already-observed sources without re-reading their skills.

4. **Evidence loading was not adequately bounded.** All 7–90 day baselines and
   full achievement models, including descriptions/media, were fetched. Only
   the earliest usable baseline and scoring fields are loaded now. Per-profile
   skills/recent achievement reads are capped with an overflow sentinel. Excess
   evidence produces `evidence_complete=false`, no automatic match, and a
   visible paused state on web/mobile. Scores are never silently computed from
   truncated evidence. Candidate user reads exclude email, passwords and other
   contact/account fields.

5. **Selected organization authority was skipped for coaches/scouts.** Personal
   role eligibility was accepted even when a selected organization membership
   had been revoked. Every selected organization now requires current
   VIEW_TALENTS authority regardless of the recipient's account role. The
   organization owner is refreshed from the database before block checks, so a
   cached preference cannot retain an old owner's scope after ownership changes.
   Block queries read only edges between the current recipient principals and
   the current candidate page, rather than materializing entire block graphs.
   Single-candidate safety checks use indexed EXISTS predicates in the database.

6. **Signing-key rotation could bypass erased weekly receipts.** An opaque
   receipt was generated only with the active key. After withdrawal erased the
   talent association, rotation could create a second receipt. The job now
   checks active and configured fallback keys, plus still-linked weekly receipts.
   Erased links stay erased; no raw talent ID is restored to an old receipt.

7. **Retention and erasure materialized whole result sets.** Cleanup collected
   every invalid talent ID and could send an unbounded notification queryset
   through Django's deletion collector. Invalid sources, expired snapshots and
   receipt erasure now use keyset groups. Erasure keeps opaque rate-limit
   receipts until expiry. Eligibility is rechecked after locks before invalid
   evidence is purged.

8. **Daily quota filters defeated timestamp indexes.** Casting created_at to a
   date required scanning recipient histories. Explicit local-day timestamp
   ranges now handle 23/25-hour days and use composite quota indexes. Additional
   indexes cover recipient scans, opted-in source scope, achievement dates,
   snapshots and receipt expiry.

9. **No bounded/resumable operator run.** The command now validates batch size
   (1–100), recipient cursor and maximum recipients before writes. It prints
   completed-group checkpoints, preserves idempotency when an interrupted group
   is repeated, and supports a write-free preview. Database cursors are not held
   open while network notification delivery runs.

Validation
----------

| Check | Result |
| --- | --- |
| Final PostgreSQL feature/audit/scale/concurrency suite | 61 passed |
| Final SQLite audit and scale suite | 20 passed |
| Broader SQLite feature/recommendation/notification/organization regressions | 127 passed |
| Mobile Rising Talent, roster and native-call checks | 26 passed |
| Mobile TypeScript, migration consistency, whitespace check | Passed |

The audit suite covers exact weekly/daily limits; erased receipts across
withdrawal/re-enrolment and key rotation; partial failure/retry; candidate
starvation; keyset resume; private/inactive sources; revoked organization scope;
owner-transfer blocks; fresh skill reads after waiting on a consent lock;
bounded evidence/erasure; DST boundaries; and constant query growth within a
group. Existing scoring, recommendation, organization badge and notification
regressions are included in the broader run.

A small structural scale check proves that 40 candidates shared by ten
recipients require 40 planning assessments, rather than 400. Snapshot creation
for 39 missing sources stays within two queries of the one-source case and
repeated observation does not read source skills again.

The larger fixture uses 1,000 candidates, 100 recipients, 3,000 achievements and
overlapping skill interests. It requires exactly 1,000 planning assessments,
retains at most 500 candidate selections and uses fewer than 300 planning
queries. Achievement descriptions and media are not selected. This is a
synthetic structural check, not a production throughput or network benchmark.

PostgreSQL tests use a fresh randomly named `test_awinlink_rising_*` database on
the verified loopback cluster whose data directory is inside this workspace.
Tests cover competing duplicate alerts, eight distinct concurrent candidates
against the five-alert daily cap, source withdrawal, duplicate snapshots,
overlapping complete jobs, and a deliberately blocked snapshot worker whose
source skills change before its consent lock becomes available. All transport
publication is mocked for those races.

Reproduce with:

```
python manage.py test recommendations.test_rising_talent recommendations.test_rising_talent_audit.RisingJobAuditTests --settings=config.rising_talent_test_settings
python scripts/rising_talent_audit.py
node --test mobile/tests/rising-talent.test.cjs
```

The PostgreSQL runner verifies the workspace cluster before creating its test
database, ignores application connection settings, and lets Django destroy the
test database when finished. Its explicit default labels include the scale and
concurrency classes. It does not start/stop a database service or send live alerts.

Remaining operating limits
--------------------------

The algorithm intentionally rescans eligible candidates for each bounded
recipient group. With R recipients, C candidates and group size B, planning work
is approximately O(ceil(R/B) × C), plus single-candidate safety checks for actual
alerts. It does not cache public identities or inferred evidence across users
or runs. Very large catalogs still need a representative throughput benchmark
before selecting a schedule or adding a persisted, consent-versioned index.
The fixed evidence ceiling prevents one profile from exhausting process memory,
but database window queries still have to inspect qualifying source rows.

Notification delivery continues to use the existing synchronous, best-effort
transport after commit. A persisted in-app notification is deduplicated even
if a remote push transport fails; this audit does not promise exactly-once
network delivery or change transport retries. Real-device delivery and hosted
database capacity were not tested, and nothing was deployed.

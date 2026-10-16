# Recommendation benchmark: PostgreSQL status and local evidence

**Date:** 2026-10-16  
**Rollout flags:** `UNIFIED_RECOMMENDATIONS_ENABLED=False`, `RECOMMENDATION_INTEREST_LEARNING_ENABLED=False`  
**Outcome:** PostgreSQL end-to-end run blocked; no PostgreSQL results are claimed.

## Environment and benchmark scope

The configured database is SQLite. There is no `DATABASE_URL`, PostgreSQL client in `PATH`, server binary in the common install locations checked, PostgreSQL Windows service, or container runtime in the workspace. The existing `audit-postgresql.json` explicitly reports offline PostgreSQL DDL compilation only. A user-scoped PostgreSQL installation attempt (`winget install PostgreSQL.PostgreSQL.17`) returned “No applicable installer found.” No test data was written to or benchmarked against PostgreSQL.

Consequently, end-to-end PostgreSQL latency, per-surface query counts, and PostgreSQL relevance/diversity results are **not measured**. This report separates runnable local evidence from that blocker rather than presenting SQLite or in-memory timings as PostgreSQL measurements.

## Available local evidence

The deterministic 40-item synthetic K=10 ordering comparison in [SHADOW_EVALUATION.md](SHADOW_EVALUATION.md) produced relevance@10 of 1.00 for legacy and revised unified ranking; topic coverage was 25% and 50%, respectively. Catalog coverage and novelty were equal. Those are in-memory ranking metrics, not database-backed relevance measurements.

The added SQLite ORM regression test captured domain/skill relation reads while adapting the same viewer and candidate twice: **4 queries on the first uncached adaptation, then 0 on the repeated adaptation**. This isolates per-request adaptation cache behavior; it is not a whole-request or PostgreSQL query count. The prior ordering-only timing run measured 0.0073 ms median for legacy sort and 0.3809 ms for revised unified selection. It excludes candidate generation, ORM, serialization, middleware, and network latency and must not be used as end-to-end latency.

The focused recommendation suite passed **27 tests**, including profile-less cold-start behavior, inferred-interest consent, private-source filtering, dismissal isolation/filtering, disabled feedback collection, and relation-cache regressions. `manage.py check` passed. The actual runtime settings remained false for both rollout flags.

## Confirmed performance changes

- Unified adaptation previously evaluated the same profile and candidate domain/skill relations repeatedly while constructing matched topics and skill boosts. It now caches those relation values and normalized topic sets for the service instance, normally one request. Relation access uses `.all()` so candidate querysets that already prefetch domains and skills can reuse their prefetch cache.
- Connection suggestions previously evaluated `values_list()` twice for the same pending/accepted connection queryset. They now fetch sender and receiver IDs together in one query.

The first change is covered by the 4-to-0 repeated-adaptation query regression test. The connection query reduction follows from the changed query shape; its full endpoint query count has not been measured on PostgreSQL.

## Cold-start and privacy status

The local tests verify that a user without a talent profile gets no invented talent, learning, event, or connection recommendations and does not trigger sub-ecosystem lookup. Existing security tests verify consent gates, private-profile/item exclusion, dismissal ownership, and disabled feedback collection. These tests run with the configured local SQLite test database; PostgreSQL-specific behavior remains unverified.

## Rollout blockers

1. Provide a reachable, disposable PostgreSQL database or an installable local PostgreSQL runtime. Then rerun the synthetic test workload on that backend; current machine has neither.
2. Run end-to-end legacy and unified surface requests against identical fixtures, recording median and p95 latency, total and per-query counts, and query plans at representative catalog sizes. Include PostgreSQL cold/warm cache and concurrency runs.
3. Replace synthetic relevance labels with representative anonymized or judged data per recommendation surface and cohort. The present labels are a mechanics check only.
4. Validate privacy filtering and opt-in behavior on the PostgreSQL-backed integration suite before enabling either flag. No production shadow telemetry or rollout evidence exists.

## Verification

`python manage.py test recommendations.test_unified recommendations.test_unified_rollout recommendations.test_interest_learning --verbosity 1`  
`python manage.py check`

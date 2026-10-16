# Unified recommendation shadow evaluation

**Date:** 2026-10-16  
**Status:** Local synthetic evaluation only; both rollout flags remain disabled.

## Result

The revised unified ranking was compared with legacy descending-score ordering on the same deterministic 40-item catalog, with K=10. Relevance labels were fixed in advance: the first two ten-item topic clusters were relevant. Items 0–4 were marked as previously seen. Prior unified results from the first run are included to show the diversity tradeoff.

| Metric at K=10 | Legacy | Prior unified | Revised unified |
| --- | ---: | ---: | ---: |
| Relevance@K | 1.00 | 0.90 | 1.00 |
| Unique topics | 1/4 | 3/4 | 2/4 |
| Topic coverage | 25% | 75% | 50% |
| Catalog coverage | 25% (10/40) | 25% (10/40) | 25% (10/40) |
| Novelty (unseen items) | 50% | 50% | 50% |
| Ranking query count | 0 | 0 | 0 |
| Median ordering latency | 0.0073 ms | 0.5909 ms | 0.3809 ms |
| p95 sampled ordering latency | 0.0120 ms | 0.6697 ms | 0.4742 ms |

Relevance-first diversity restored relevance@10 to legacy parity while retaining one additional topic over legacy. It gives up one topic versus the prior, more aggressive diversity setting. The revised algorithm trims weak tails when at least three candidates meet its relevance band and adds a bounded nudge for direct normalized skill matches. The adaptive limit remained ten on this catalog, so the comparison uses the same K.

Latency is from 500 in-memory ordering iterations in this local Python/SQLite environment. The prior and revised timings are separate runs and machine timing varies; neither is production service latency. Both exclude candidate retrieval, ORM work, serialization, request middleware, network time, and production load. The measured zero query count is only for in-memory ranking, not each surface's candidate-generation path. Catalog coverage is mechanically fixed by returning 10 distinct items from a 40-item catalog.

## Security and behavior checks

`manage.py test recommendations.test_unified recommendations.test_unified_rollout recommendations.test_interest_learning --verbosity 1` passed **25 tests**. New regression coverage checks relevance-band limits, adaptive truncation, normalized skill matching, and profile-less cold-start behavior. The suite also covers legacy fallback with the flag off, inferred-interest consent, private-source filtering, dismissal filtering and per-user isolation, and refusal to collect feedback while both flags are disabled. Opt-in tests use test-only setting overrides; environment settings remained disabled.

Runtime settings inspection reported `UNIFIED_RECOMMENDATIONS_ENABLED=False`, `RECOMMENDATION_INTEREST_LEARNING_ENABLED=False`, and SQLite as the configured database. The harness creates no activity or recommendation feedback records.

## Rollout blockers

1. There is no representative judged production dataset. Synthetic labels show the mechanics but cannot establish user benefit. Build an offline set with trustworthy judgments, separated by surface and user cohort, before settling diversity weights.
2. Candidate-generation SQL was not included in this measurement. Profile query counts and latency per surface using production-like PostgreSQL data and representative catalog sizes, with cold and warm cache runs and concurrency.
3. Novelty uses a synthetic seen-ID set. Validate real exposure history and define an agreed novelty measure; these results do not demonstrate improved discovery.
4. No production shadow telemetry or controlled rollout evidence was collected. Keep both flags disabled until privacy and consent checks are reviewed against representative data and relevance, latency, and query budgets meet agreed thresholds.

## Reproduction

Run `python manage.py shell -c "from recommendations.shadow_evaluation import run; print(run())"` to reproduce the synthetic comparison, including adaptive limits and relevance-band diversity. Timings vary by machine and should not be compared across environments as service latency.

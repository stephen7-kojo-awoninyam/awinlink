Local fictional recommendation sandbox
======================================

Run from the repository root with the project's virtual environment:

```powershell
.venv\Scripts\python.exe manage.py migrate --settings=config.recommendation_seed_settings --noinput
.venv\Scripts\python.exe -u manage.py seed_recommendation_users --settings=config.recommendation_seed_settings --extended --evaluate --report recommendations/local_benchmark_results.json
.venv\Scripts\python.exe manage.py test recommendations.test_seed recommendations.test_local_benchmark --settings=config.recommendation_seed_settings --noinput
```

This creates `recommendation-seed.sqlite3`, separate from `db.sqlite3` and
`DATABASE_URL`. The command rejects other file databases, DEBUG=False, and
recognized hosted environments. No deployment or external service is needed.
Accounts have unusable passwords and example.invalid email addresses. Reruns
reuse the same usernames and restore their fictional profile data. Conflicting
accounts cause the whole seed transaction to roll back.

The original 90 public talent profiles form nine authored cohorts of ten,
spanning sports, technology, arts, and public speaking. Country and experience
vary. Without `--extended`, the command retains its original 90-user talent-only
seed and benchmark behavior.

`--extended` adds nine users: three without profiles, three with empty profiles,
and three with domain/skill profiles but no recommendation activity. Each group
spans Football, Software, and Music. Their authored preferences are withheld
from the engine in the no-profile and empty-profile groups. This separates a
missing profile from a new user who has supplied interests. Existing seeded
users receive course authorship, enrollment, and application fixtures; the nine
cold-start users receive none of those interactions.

The additional catalogs contain 90 opportunities (63 eligible plus inactive,
expired, and closed-organization distractors), 90 courses (63 approved plus
draft, pending, and rejected distractors), and 72 organizations (63 active and
nine closed). Applications, creator ownership, and enrollments supply per-user
exclusions. Reruns reuse these objects and refresh deadlines relative to today.

The extended benchmark requests five results on four surfaces for all 99 users,
under both pipeline settings. It emits 32 separate reports: four surfaces times
four user segments times two pipelines. `--surfaces opportunities courses
organizations` can restrict surfaces; `--pipeline legacy` or `--pipeline unified`
selects one pipeline. Pipeline flags are explicit and activity-interest inference
is off. Each user request creates a fresh recommendation service. No benchmark
code removes or repairs returned recommendations before measuring them.

Organizations have no unified adapter. Both settings call the existing
organization recommender and are labeled `shared_legacy_no_unified_adapter`;
these are two measurements of the same backend, not two ranking implementations.

The fixture manifest labels cohort relevance independently of recommendation
scores. Eligibility is authored from fixture statuses and per-user exclusions.
Unknown items, duplicate items, self-recommendations, and ineligible items never
earn relevance credit. Percentages are computed from total counts within each
surface/segment, rather than averaging per-user percentages:

| Metric | Numerator / denominator |
| --- | --- |
| Precision@5 | Distinct eligible same-cohort results / all returned results |
| Topic precision@5 | Distinct same-cohort results, regardless of eligibility / returned results |
| Eligible result rate | Distinct eligible results / returned results |
| Slot relevance@5 | Eligible same-cohort results / requested slots (5 per user) |
| User coverage | Users receiving any results / users evaluated |
| Recall@5 | Eligible same-cohort results / all eligible same-cohort candidates for these viewers |

When no results are returned, precision and eligible result rate are JSON `null`
(undefined); coverage and slot relevance are 0%. A cold-start abstention does
not imply an inaccurate ranking. Hidden-preference precision is only a small
synthetic fallback check, not evidence of personalization without input.
Latency covers the full ORM-backed engine call, including unified adaptation.
Report generation and manifest construction are outside that timing.

This deliberately simple synthetic smoke benchmark does not estimate production
accuracy, click-through rate, user satisfaction, or production load capacity.

Extended results (2026-10-18)
-----------------------------

All 16 tests passed, including every cohort on the new surfaces, cold-start
behavior in both pipelines, exclusion rules, fixture repeatability, rollback,
local-only guards, and metric handling for duplicates and abstentions.

For the 90 profiled users, the measured eligible precision@5 is:

| Surface | Legacy | Unified setting | User coverage (both) | Recall@5 (both) |
| --- | ---: | ---: | ---: | ---: |
| Talents | 100% | 100% | 100% | 51.72% |
| Opportunities | 100% | 100% | 100% | 72.46% |
| Courses | 100% | 100% | 100% | 80.65% |
| Organizations (shared backend) | 80% | 80% | 100% | 57.14% |

Each surface returned 450 results per pipeline. Talents, opportunities, and
courses had 450 eligible relevant results; organizations had 360. Organization
topic precision was 100%, but 90 returned organizations were closed. The current
organization recommender does not filter organization status. This extension
measures that existing gap and does not change production ranking or filtering.

Cold-start eligible precision@5 was identical in the two runs:

| User segment (3 users each) | Talents | Opportunities | Courses | Organizations (shared backend) |
| --- | ---: | ---: | ---: | ---: |
| Profile with interests, no activity | 100% | 100% | 100% | 80% |
| Empty profile | N/A | 33.33% | 0% | 0% |
| No profile | N/A | N/A | N/A | 0% |

N/A means no results: 0% user coverage and 0% slot relevance. Every other cell
had 100% user coverage. All organization results for no-profile and empty-profile
users were closed, so their eligible result rate was 0%. Generic empty-profile
opportunity and course results were eligible, but matched only 5/15 and 0/15
held-out cohort labels, respectively. Each cold-start segment is deliberately
small; these percentages are diagnostic fixture results, not population estimates.

The JSON artifact `local_benchmark_results.json` contains all 32 reports,
counts, denominators, coverage, eligibility, recall, mean latency, and P95 latency.
The test suite overlapped the legacy benchmark pass, so timing differences
between pipelines are not a controlled comparison.

Original baseline, validated locally on 2026-10-18: all seven seed tests passed. Both pipelines
achieved 100% precision@5, 100% slot relevance, 100% user coverage, and 55.56%
recall@5 across all 90 fictional users (450 relevant recommendations each).

| Pipeline | Mean latency | P95 latency |
| --- | ---: | ---: |
| Legacy | 1808.45 ms | 2540.75 ms |
| Unified | 1554.39 ms | 2153.22 ms |

These are single-pass local measurements, not a controlled speed comparison.
The two passes ran sequentially, so cache warmth and background activity differ.
The original baseline predates extended catalogs and cold-start candidates;
use `local_benchmark_results.json` for the current extended measurements.

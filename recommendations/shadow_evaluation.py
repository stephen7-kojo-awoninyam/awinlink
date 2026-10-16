"""Deterministic, local shadow comparison for the unified ranking adapter.

Run with ``python manage.py shell -c "from recommendations.shadow_evaluation
import run; print(run())"``. This synthetic benchmark never writes activity.
"""
from statistics import median
from time import perf_counter

from django.db import connection
from django.test.utils import CaptureQueriesContext

from recommendations.unified import (
    adaptive_recommendation_limit,
    diversify_recommendations,
)


def _catalog():
    topics = ("artificial intelligence", "sports science", "mental health", "coaching")
    # Explicit synthetic judgments: the first two topic clusters are relevant.
    return [
        {
            "item_id": index,
            "score": float(100 - index),
            "matched_topics": [topics[index // 10]],
            "relevant": index // 10 in (0, 1),
        }
        for index in range(40)
    ]


def _metrics(rows, catalog, k=10):
    top = rows[:k]
    return {
        "relevance_at_k": round(sum(row["relevant"] for row in top) / k, 4),
        "unique_topics_at_k": len({topic for row in top for topic in row["matched_topics"]}),
        "topic_coverage_at_k": round(
            len({topic for row in top for topic in row["matched_topics"]}) / 4, 4
        ),
        "catalog_coverage_at_k": round(len({row["item_id"] for row in top}) / len(catalog), 4),
        # IDs 0-4 represent the viewer's previously seen items.
        "novelty_at_k": round(sum(row["item_id"] >= 5 for row in top) / k, 4),
    }


def run(repeats=500, k=10):
    catalog = _catalog()
    legacy = sorted(catalog, key=lambda row: row["score"], reverse=True)
    unified = _rank_unified(catalog, k)
    results = {"legacy": _metrics(legacy, catalog, k), "unified": _metrics(unified, catalog, k)}

    # Query counts are measured around the same in-memory ranking operation.
    # The ranking adapter is not expected to fetch candidates itself.
    with CaptureQueriesContext(connection) as captured:
        _rank_unified(catalog, k)
    results["query_count_per_ranking"] = len(captured)

    samples = {"legacy": [], "unified": []}
    for _ in range(repeats):
        start = perf_counter()
        sorted(catalog, key=lambda row: row["score"], reverse=True)[:k]
        samples["legacy"].append((perf_counter() - start) * 1000)
        start = perf_counter()
        _rank_unified(catalog, k)
        samples["unified"].append((perf_counter() - start) * 1000)
    results["latency_ms"] = {
        name: {"median": round(median(values), 4), "p95_sample": round(sorted(values)[int(.95 * (len(values) - 1))], 4)}
        for name, values in samples.items()
    }
    results["methodology"] = {
        "catalog_size": len(catalog),
        "k": k,
        "relevance_judgments": "synthetic fixed topic labels; clusters 0 and 1 relevant",
        "seen_items": [0, 1, 2, 3, 4],
        "timing_repeats": repeats,
        "timing_scope": "in-memory ordering only; excludes ORM, serialization, network and candidate generation",
        "database": connection.vendor,
    }
    return results


def _rank_unified(catalog, k):
    adaptive_limit = adaptive_recommendation_limit(catalog, requested=k)
    return diversify_recommendations(catalog, limit=adaptive_limit)

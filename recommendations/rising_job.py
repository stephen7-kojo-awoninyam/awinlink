"""Bounded recipient groups share candidate scoring; writes recheck one candidate."""
from collections import Counter, defaultdict
from heapq import heappush, heapreplace
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from .models import RisingTalentAlert as Alert, RisingTalentPreference as Preference
from .rising_talent import (BATCH_SIZE, MAX_DAILY_ALERTS, alert_keys, build_context,
                            candidate_matches, day_bounds, keyset_batches, notify_match)


def recipient_batches(batch_size=BATCH_SIZE, after=0):
    rows = Preference.objects.filter(alerts_enabled=True, user__is_active=True,
        user__role__in=["ORGANIZATION", "SCOUT", "COACH"]).select_related("user", "organization").prefetch_related("skills")
    return keyset_batches(rows, batch_size, after)


def plan_alerts(preferences, day):
    """Return at most five compact candidates per recipient; skip weekly receipts."""
    contexts = {}
    for preference in preferences:
        context = build_context(preference.user, preference)
        if context:
            contexts[preference.user_id] = context
    start, end = day_bounds(day)
    period = day - timedelta(days=day.weekday())
    used, daily, linked = defaultdict(set), Counter(), defaultdict(set)
    rows = Alert.objects.filter(recipient_id__in=contexts).filter(
        Q(period=period) | Q(created_at__gte=start, created_at__lt=end)
    ).values("recipient_id", "deduplication_key", "talent_id", "period", "created_at")
    for row in rows.iterator(chunk_size=BATCH_SIZE):
        user_id = row["recipient_id"]
        if row["period"] == period:
            used[user_id].add(row["deduplication_key"])
            linked[user_id].add(row["talent_id"])
        if start <= row["created_at"] < end:
            daily[user_id] += 1
    contexts = {key: value for key, value in contexts.items() if daily[key] < MAX_DAILY_ALERTS}
    heaps = defaultdict(list)
    for user_id, row in candidate_matches(contexts, day):
        talent_id = row["talent_id"]
        if talent_id in linked[user_id] or used[user_id].intersection(alert_keys(user_id, talent_id, period)):
            continue
        item = (row["assessment"]["score"], -talent_id, talent_id)
        heap = heaps[user_id]
        if len(heap) < MAX_DAILY_ALERTS - daily[user_id]:
            heappush(heap, item)
        elif item > heap[0]:
            heapreplace(heap, item)
    return [(contexts[user_id].user, [item[2] for item in sorted(heap, reverse=True)])
            for user_id, heap in sorted(heaps.items())]


def run_alerts(*, dry_run=False, batch_size=BATCH_SIZE, after=0, max_recipients=None, progress=None):
    matches = sent = processed = 0
    cursor = after
    for batch in recipient_batches(batch_size, after):
        if max_recipients is not None:
            batch = batch[:max_recipients - processed]
        # A fresh day per group handles jobs that run across local midnight.
        for user, talent_ids in plan_alerts(batch, timezone.localdate()):
            matches += len(talent_ids)
            if not dry_run:
                for talent_id in talent_ids:
                    sent += notify_match(user, talent_id)
        processed += len(batch)
        cursor = batch[-1].pk
        if progress:
            progress(cursor, processed)
        if max_recipients is not None and processed >= max_recipients:
            break
    return {"matches": matches, "alerts": sent, "processed": processed, "recipient_after": cursor}

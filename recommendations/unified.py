"""Consistent result envelopes over Awinlink's established recommenders.

This layer intentionally leaves candidate selection and scoring in the existing
recommendation engine. Feed callers pass their already privacy-filtered rows.
"""

from recommendations.ecosystems import normalize_topic
from recommendations.services import RecommendationEngine
from recommendations.interest_learning import (
    InterestLearningService,
    interest_learning_enabled,
    is_sensitive_topic,
)
from django.core.exceptions import ObjectDoesNotExist


def unified_recommendations_enabled():
    """Return the rollout flag; absent settings always means legacy behavior."""
    from django.conf import settings

    return bool(getattr(settings, "UNIFIED_RECOMMENDATIONS_ENABLED", False))


def adaptive_recommendation_limit(results, requested=None, maximum=12, minimum=3):
    """Use score confidence to avoid padding a list with weak candidates.

    The requested value is a ceiling. When at least ``minimum`` candidates
    remain within a conservative relevance band, lower-scoring tail rows are
    omitted. Small catalogs are never padded or discarded.
    """
    count = len(results)
    if not count:
        return 0
    ceiling = min(count, max(1, requested if requested is not None else maximum))
    top_score = max(float(row.get("score", 0) or 0) for row in results)
    if top_score <= 0:
        return ceiling
    floor = max(top_score * 0.75, top_score - 15.0)
    confident_count = sum(float(row.get("score", 0) or 0) >= floor for row in results)
    if confident_count >= minimum:
        return min(ceiling, confident_count)
    return ceiling


def diversify_recommendations(results, limit=None):
    """Keep relevance primary and use topic novelty only within a 10% score band.

    A lower-scoring candidate can only move ahead of the current best when it
    is close in score and introduces a new topic. Display scores stay intact.
    """
    remaining = list(enumerate(results))
    selected = []
    covered_topics = set()
    while remaining and (limit is None or len(selected) < limit):
        top_score = max(float(row.get("score", 0) or 0) for _, row in remaining)
        band = max(1.0, abs(top_score) * 0.10)
        near_best = [
            (position, original_index, row)
            for position, (original_index, row) in enumerate(remaining)
            if float(row.get("score", 0) or 0) >= top_score - band
        ]
        best_position, _, chosen = max(
            near_best,
            key=lambda value: (
                len(set(value[2].get("matched_topics", ())) - covered_topics),
                float(value[2].get("score", 0) or 0),
                -value[1],
            ),
        )
        remaining.pop(best_position)
        selected.append(chosen)
        covered_topics.update(chosen.get("matched_topics", ()))
    return selected


class UnifiedRecommendationService:
    """Adapt existing recommendation results to a shared, explainable shape."""

    def __init__(self, engine=None):
        self.engine = engine or RecommendationEngine()
        self._topic_cache = {}
        # These caches live for one service instance (normally one request),
        # avoiding repeated ORM relation reads while adapting the same rows.
        self._object_topics = {}
        self._object_relations = {}

    @staticmethod
    def _profile_for(viewer):
        for relation_name in (
            "talent_profile", "coach_profile", "scout_profile", "organization_profile",
        ):
            try:
                profile = getattr(viewer, relation_name, None)
            except ObjectDoesNotExist:
                profile = None
            if profile is not None:
                return profile
        if hasattr(viewer, "domains") or hasattr(viewer, "skills"):
            return viewer
        return None

    @staticmethod
    def _object_cache_key(value):
        pk = getattr(value, "pk", None)
        return (type(value), pk) if pk is not None else (type(value), id(value))

    def _topics_for(self, talent):
        if not talent:
            return set()
        cache_key = self._object_cache_key(talent)
        if cache_key in self._object_topics:
            return self._object_topics[cache_key]
        topics = set()
        for relation_name in ("domains", "skills"):
            values = self._relation_values(talent, relation_name)
            topics.update(topic for topic in map(normalize_topic, values) if topic)
        for field in ("domain", "category", "talent_area", "specialization", "focus"):
            value = getattr(talent, field, None)
            value = getattr(value, "name", value)
            topic = normalize_topic(value)
            if topic:
                topics.add(topic)
        self._object_topics[cache_key] = topics
        return topics

    def _viewer_topics(self, viewer):
        profile = self._profile_for(viewer)
        if profile is None:
            return set()
        topics = set(self._topics_for(profile))
        owner = getattr(profile, "user", None) or viewer
        owner_id = getattr(owner, "pk", None)
        if owner_id is not None and owner_id not in self._topic_cache:
            ecosystem_topics = set()
            if getattr(owner, "is_authenticated", False):
                ecosystem_rows = self.engine.recommend_sub_ecosystems(owner)
                ecosystem_topics = {
                    normalize_topic(row.get("focus", ""))
                    for row in ecosystem_rows
                    if row.get("focus")
                }
            self._topic_cache[owner_id] = ecosystem_topics
        if owner_id is not None:
            topics.update(self._topic_cache.get(owner_id, set()))
        return topics

    def _matched_topics(self, viewer, item, extra=()):
        source = self._viewer_topics(viewer)
        target_talent = getattr(item, "talent", None)
        target = set(self._topics_for(target_talent or item))
        fields = ("title", "description", "name", "focus")
        text = " ".join(str(getattr(item, field, "") or "") for field in fields)
        target.update(topic for topic in source if topic and topic in normalize_topic(text))
        return sorted(source & target | {normalize_topic(value) for value in extra if value})

    def _match_boost(self, viewer, item, matched_topics):
        """Give direct skill overlap a small, bounded nudge over legacy scores."""
        profile = self._profile_for(viewer) or viewer
        viewer_skills = self._topics_for(profile) & {
            normalize_topic(value)
            for value in self._relation_values(profile, "skills")
        }
        item_skills = {
            normalize_topic(value) for value in self._relation_values(item, "skills")
        }
        exact_skills = viewer_skills & item_skills
        skill_boost = min(6.0, 3.0 * len(exact_skills))
        topic_boost = min(3.0, 1.5 * len(set(matched_topics) - exact_skills))
        return skill_boost + topic_boost

    def _relation_values(self, item, relation_name):
        cache_key = (self._object_cache_key(item), relation_name)
        if cache_key in self._object_relations:
            return self._object_relations[cache_key]
        relation = getattr(item, relation_name, None)
        if relation is None:
            values = []
        else:
            if hasattr(relation, "all"):
                values = [getattr(value, "name", value) for value in relation.all()]
            else:
                try:
                    values = list(relation.values_list("name", flat=True))
                except AttributeError:
                    values = [getattr(value, "name", value) for value in relation]
        self._object_relations[cache_key] = values
        return values

    def _result(self, kind, viewer, item, score, reasons=(), extra_topics=()):
        reason_list = [str(reason) for reason in reasons if reason]
        topics = self._matched_topics(viewer, item, extra_topics)
        explanation = "; ".join(reason_list)
        if not explanation and topics:
            explanation = "Matches your interests in " + ", ".join(topics) + "."
        if not explanation:
            explanation = "Recommended based on your profile and activity."
        score = min(100.0, float(score) + self._match_boost(viewer, item, topics))
        return {
            "kind": kind,
            "item": item,
            "feedback_item_kind": kind.upper(),
            "feedback_item_id": getattr(item, "pk", None),
            "score": float(score),
            "matched_topics": topics,
            "explanation": explanation,
        }

    def _adapt(self, kind, viewer, rows, object_key, reason_key=None, reasons_key=None):
        results = []
        for row in rows:
            item = row[object_key]
            reason = row.get(reason_key) if reason_key else None
            reasons = row.get(reasons_key, ()) if reasons_key else ()
            if reason:
                reasons = [reason]
            results.append(self._result(kind, viewer, item, row.get("score", 0), reasons))
        return results

    def _finalize(self, viewer, kind, results, limit=None):
        owner = getattr(viewer, "user", None) or viewer
        if not getattr(owner, "is_authenticated", False):
            return diversify_recommendations(results, limit=limit)

        dismissed_ids = InterestLearningService.dismissed_item_ids(owner, kind)
        results = [
            row for row in results
            if row.get("feedback_item_id", getattr(row["item"], "pk", None)) not in dismissed_ids
        ]

        if interest_learning_enabled() and unified_recommendations_enabled():
            learned = InterestLearningService.active_topic_strengths(owner)
            if learned:
                for row in results:
                    item = row["item"]
                    if kind == "FEED" and hasattr(item, "post"):
                        item = item.post
                    candidate_topics = InterestLearningService._candidate_topics(item, kind)
                    candidate_text = InterestLearningService._candidate_text(item, kind)
                    matches = sorted(
                        topic for topic in learned
                        if (
                            topic in candidate_topics
                            or InterestLearningService._topic_in_text(topic, candidate_text)
                        ) and not is_sensitive_topic(topic)
                    )
                    if not matches:
                        continue
                    row["learned_interest_topics"] = matches
                    row["matched_topics"] = sorted(set(row["matched_topics"]) | set(matches))
                    boost = min(8.0, 8.0 * max(learned[topic] for topic in matches))
                    row["score"] = min(100.0, row["score"] + boost)
                    row["explanation"] += (
                        " Matches interests inferred from your activity: "
                        + ", ".join(matches) + "."
                    )
        effective_limit = adaptive_recommendation_limit(results, requested=limit)
        return diversify_recommendations(results, limit=effective_limit)

    def recommend_talents(self, user, limit=12):
        talent = getattr(user, "talent_profile", None)
        rows = self.engine.recommend_talents_for_talent(talent, limit=limit) if talent else []
        results = self._adapt("talent", talent, rows, "talent", reasons_key="reasons")
        for result, row in zip(results, rows):
            result["discovery_type"] = row.get("discovery_type")
        return self._finalize(talent, "TALENT", results, limit=limit)

    def recommend_connections(self, user, limit=12):
        """Public, relevant people, using the existing talent discovery exclusions."""
        talent = getattr(user, "talent_profile", None)
        rows = self.engine.recommend_talents_for_talent(talent, limit=100) if talent else []
        if rows:
            from connections.models import Connection
            from django.db.models import Q

            requests = Connection.objects.filter(
                status__in=("PENDING", "ACCEPTED"),
            ).filter(Q(sender=user) | Q(receiver=user))
            blocked_ids = {
                user_id
                for sender_id, receiver_id in requests.values_list("sender_id", "receiver_id")
                for user_id in (sender_id, receiver_id)
            }
            rows = [row for row in rows if row["talent"].user_id not in blocked_ids
                    and row["talent"].user.is_active][:limit]
        results = self._adapt("connection", talent, rows, "talent", reasons_key="reasons")
        return self._finalize(talent, "CONNECTION", results, limit=limit)

    def recommend_opportunities(self, user, limit=10):
        rows = self.engine.recommend_opportunities_for_user(user, limit=limit)
        return self._finalize(
            user, "OPPORTUNITY", self._adapt("opportunity", user, rows, "opportunity"), limit=limit
        )

    def recommend_learning(self, user, limit=10, candidates=None):
        talent = getattr(user, "talent_profile", None)
        if candidates is None:
            rows = self.engine.recommend_courses_for_talent(talent, limit=limit) if talent else []
        elif talent:
            rows = []
            for course in candidates:
                score = self.engine.score_course_for_talent(talent, course)
                if score > 0:
                    rows.append({
                        "course": course,
                        "score": score,
                        "reason": self.engine.get_course_recommendation_reason(talent, course),
                    })
            rows.sort(key=lambda row: row["score"], reverse=True)
        else:
            rows = []
        return self._finalize(
            talent, "LEARNING",
            self._adapt("learning", talent, rows, "course", reason_key="reason"),
            limit=limit,
        )

    def recommend_events(self, user, limit=10):
        talent = getattr(user, "talent_profile", None)
        rows = self.engine.recommend_events_for_talent(talent, limit=limit) if talent else []
        return self._finalize(
            talent, "EVENT", self._adapt("event", talent, rows, "event", reason_key="reason"),
            limit=limit,
        )

    def rank_feed_items(self, user, feed_items, limit=None):
        """Score already-authorized feed entries without changing feed visibility.

        Entries are either model instances or mappings with ``object`` and
        optional ``type`` keys. Existing feed code remains responsible for the
        visibility and relationship queryset used to produce these entries.
        """
        ranked = []
        for entry in feed_items:
            item = entry.get("object") if isinstance(entry, dict) else entry
            if item is None:
                continue
            is_share = isinstance(entry, dict) and str(entry.get("type", "")).upper() == "SHARE"
            score_item = item.post if is_share else item
            score = self.engine.score_post_for_user(user, score_item)
            if is_share and entry.get("shared_by_in_network"):
                score += 10
            reasons = []
            topics = self._matched_topics(user, score_item)
            if topics:
                reasons.append("Matches your interests in " + ", ".join(topics))
            if not reasons:
                reasons.append("Ranked using your existing feed relevance signals")
            result = self._result("feed", user, score_item, score, reasons, topics)
            result["item"] = item
            result["feedback_item_id"] = getattr(score_item, "pk", None)
            if isinstance(entry, dict) and entry.get("type"):
                result["feed_type"] = entry["type"]
            result["feed_entry"] = entry
            entry_created_at = entry.get("created_at") if isinstance(entry, dict) else None
            ranked.append((result, entry_created_at or getattr(item, "created_at", None)))
        ranked.sort(key=lambda pair: (pair[0]["score"], pair[1]), reverse=True)
        return self._finalize(
            user, "FEED", [result for result, _ in ranked], limit=limit
        )

"""Privacy-limited, opt-in interest inference from first-party activity."""

import math
import re
from collections import defaultdict

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from recommendations.ecosystems import normalize_topic
from recommendations.models import RecommendationFeedback, RecommendationInterestPreference


# These topics can reveal sensitive traits even when attached to ordinary
# content. Do not infer or return them from behavioral activity.
SENSITIVE_TOPIC_TERMS = frozenset({
    "religion", "religious", "politics", "political", "race", "racial",
    "ethnicity", "ethnic", "sex", "sexuality", "sexual orientation", "gender", "gender identity",
    "disability", "medical", "health", "disease", "diagnosis", "mental health",
    "union", "immigration", "citizenship", "age", "income", "genetic",
    "biometric", "pregnancy", "fertility",
})

SIGNAL_WEIGHTS = {
    "follow": 2.0,
    "like": 1.0,
    "save": 1.5,
    "application": 4.0,
    "enrollment": 4.0,
}
MAX_ACTIVITY_ROWS_PER_SIGNAL = 500


def interest_learning_enabled():
    return bool(getattr(settings, "RECOMMENDATION_INTEREST_LEARNING_ENABLED", False))


def is_sensitive_topic(topic):
    normalized = normalize_topic(topic)
    if not normalized:
        return True
    return any(
        normalized == term or normalized.startswith(term + " ") or (" " + term + " ") in (" " + normalized + " ")
        for term in SENSITIVE_TOPIC_TERMS
    )


class InterestLearningService:
    """Compute decayed topics on demand; raw activity and inferred profiles are not stored."""

    @staticmethod
    def preference_for(user):
        if not user or not user.is_authenticated:
            return None
        return RecommendationInterestPreference.objects.filter(user=user).first()

    @staticmethod
    def set_inferred_interests(user, enabled):
        preference, _ = RecommendationInterestPreference.objects.get_or_create(user=user)
        if preference.inferred_interests_enabled != enabled:
            preference.inferred_interests_enabled = enabled
            preference.save(update_fields=("inferred_interests_enabled", "updated_at"))
        return preference

    @staticmethod
    def _labels_for_talent(profile):
        labels = []
        if not profile or getattr(profile, "profile_visibility", None) != "PUBLIC":
            return labels
        labels.extend(domain.name for domain in profile.domains.all())
        for skill in profile.skills.all():
            labels.append(skill.name)
            labels.extend(
                relation.related_skill.name
                for relation in skill.related_skills.all()
                if float(relation.strength) >= 0.5
            )
        return labels

    @staticmethod
    def _candidate_topics(item, kind):
        labels = []
        if kind in {"TALENT", "CONNECTION"}:
            labels.extend(InterestLearningService._labels_for_talent(item))
        elif kind == "OPPORTUNITY":
            if item.domain_id:
                labels.append(item.domain.name)
            labels.extend(item.skills.values_list("name", flat=True))
            labels.extend((item.title, item.description))
        elif kind == "LEARNING":
            if item.category_id:
                labels.append(item.category.name)
            labels.extend((item.title, item.description))
        elif kind == "EVENT":
            if item.category_id:
                labels.append(item.category.name)
                if item.category.domain_id:
                    labels.append(item.category.domain.name)
            labels.extend((item.title, item.description))
        elif kind == "FEED":
            labels.append(item.caption)
            if item.talent_id:
                labels.extend(InterestLearningService._labels_for_talent(item.talent))
            if item.organization_id and item.organization.domain_id:
                labels.append(item.organization.domain.name)
        return {
            topic for topic in (normalize_topic(label) for label in labels)
            if topic and not is_sensitive_topic(topic)
        }

    @staticmethod
    def _candidate_text(item, kind):
        if kind == "FEED":
            return normalize_topic(getattr(item, "caption", ""))
        if kind in {"OPPORTUNITY", "LEARNING", "EVENT"}:
            return normalize_topic(
                f"{getattr(item, 'title', '')} {getattr(item, 'description', '')}"
            )
        return ""

    @staticmethod
    def _topic_in_text(topic, text):
        return bool(text and re.search(rf"(?<!\w){re.escape(topic)}(?!\w)", text))

    @staticmethod
    def _eligible_item(user, kind, item_id):
        from applications.models import Application
        from connections.models import Connection, Follow
        from events.models import Event, EventRegistration
        from feed.models import Post
        from learning.models import Course, Enrollment
        from opportunities.models import Opportunity
        from talents.models import TalentProfile

        if kind == "FEED":
            return Post.objects.filter(pk=item_id).filter(
                Q(visibility="PUBLIC") | Q(author=user)
            ).first()
        if kind in {"TALENT", "CONNECTION"}:
            talent = TalentProfile.objects.filter(
                pk=item_id,
                profile_visibility="PUBLIC",
                user__is_active=True,
            ).exclude(user=user).first()
            if not talent:
                return None
            blocked = Follow.objects.filter(follower=user, following=talent.user).exists()
            blocked |= Connection.objects.filter(
                Q(sender=user, receiver=talent.user) | Q(sender=talent.user, receiver=user),
                status__in=("PENDING", "ACCEPTED"),
            ).exists()
            return None if blocked else talent
        if kind == "OPPORTUNITY":
            talent = getattr(user, "talent_profile", None)
            if not talent:
                return None
            opportunity = Opportunity.objects.filter(
                pk=item_id,
                active=True,
                organization__status="ACTIVE",
            ).filter(Q(deadline__isnull=True) | Q(deadline__gte=timezone.localdate())).first()
            if not opportunity or Application.objects.filter(talent=talent, opportunity=opportunity).exists():
                return None
            return opportunity
        if kind == "LEARNING":
            course = Course.objects.filter(pk=item_id, status="APPROVED").exclude(creator=user).first()
            if not course or Enrollment.objects.filter(user=user, course=course).exists():
                return None
            return course
        if kind == "EVENT":
            now = timezone.now()
            event = Event.objects.filter(
                pk=item_id,
                status="PUBLISHED",
                organizer__status="ACTIVE",
                registration_deadline__gt=now,
                end_date__gt=now,
            ).first()
            if not event:
                return None
            if EventRegistration.objects.filter(event=event, talent__user=user).exclude(
                status__in=("CANCELLED", "REJECTED")
            ).exists():
                return None
            if event.capacity and event.registrations.filter(
                status__in=("REGISTERED", "APPROVED", "ATTENDED")
            ).count() >= event.capacity:
                return None
            return event
        return None

    @classmethod
    def record_feedback(cls, user, item_kind, item_id, action):
        kind = str(item_kind).upper()
        action = str(action).upper()
        if kind not in RecommendationFeedback.ItemKind.values or action not in RecommendationFeedback.Action.values:
            return False
        if not cls._eligible_item(user, kind, item_id):
            return False
        now = timezone.now()
        with transaction.atomic():
            feedback, created = RecommendationFeedback.objects.get_or_create(
                user=user,
                item_kind=kind,
                item_id=item_id,
                action=action,
                defaults={"last_seen_at": now},
            )
            if not created:
                RecommendationFeedback.objects.filter(pk=feedback.pk).update(last_seen_at=now)
        return True

    @classmethod
    def record_feedback_bulk(cls, user, entries, action):
        # Validate the full request first, then persist atomically. Duplicate IDs
        # in a batch are collapsed before touching the unique feedback rows.
        unique_entries = {(str(kind).upper(), int(item_id)) for kind, item_id in entries}
        if any(
            kind not in RecommendationFeedback.ItemKind.values
            or not cls._eligible_item(user, kind, item_id)
            for kind, item_id in unique_entries
        ):
            return False
        with transaction.atomic():
            for kind, item_id in unique_entries:
                cls.record_feedback(user, kind, item_id, action)
        return True

    @classmethod
    def inferred_interests(cls, user, limit=20):
        preference = cls.preference_for(user)
        if not interest_learning_enabled() or not preference or not preference.inferred_interests_enabled:
            return []

        from applications.models import Application
        from connections.models import Follow, OrganizationFollow
        from events.models import EventLike
        from feed.models import PostLike, SavedPost
        from learning.models import CourseLike, Enrollment

        half_life = max(1, int(getattr(settings, "RECOMMENDATION_INTEREST_HALF_LIFE_DAYS", 60)))
        now = timezone.now()
        half_life_seconds = half_life * 86400
        topic_scores = defaultdict(float)
        topic_sources = defaultdict(set)
        seen = set()

        def add_activity(source, item_key, timestamp, labels, weight):
            if not timestamp:
                return
            age = max(0.0, (now - timestamp).total_seconds())
            decayed_weight = weight * math.exp(-math.log(2) * age / half_life_seconds)
            for label in set(labels):
                topic = normalize_topic(label)
                key = (source, item_key, topic)
                if not topic or is_sensitive_topic(topic) or key in seen:
                    continue
                seen.add(key)
                topic_scores[topic] += decayed_weight
                topic_sources[topic].add(source)

        # Followed profiles are considered only when their talent topics are public.
        followed_profiles = Follow.objects.filter(
            follower=user,
            following__is_active=True,
        ).filter(
            Q(following__talent_profile__profile_visibility="PUBLIC")
            | Q(following__organization_profile__status="ACTIVE")
        ).select_related(
            "following__talent_profile", "following__organization_profile__domain",
        ).prefetch_related(
            "following__talent_profile__domains",
            "following__talent_profile__skills__related_skills__related_skill",
        ).order_by("-created_at")[:MAX_ACTIVITY_ROWS_PER_SIGNAL]
        for follow in followed_profiles:
            profile = getattr(follow.following, "talent_profile", None)
            labels = cls._labels_for_talent(profile)
            organization = getattr(follow.following, "organization_profile", None)
            if organization and organization.status == "ACTIVE" and organization.domain_id:
                labels.append(organization.domain.name)
            add_activity("follows", ("user", follow.following_id), follow.created_at,
                         labels, SIGNAL_WEIGHTS["follow"])

        organizations = OrganizationFollow.objects.filter(
            user=user, organization__status="ACTIVE",
        ).select_related("organization__domain").order_by("-created_at")[:MAX_ACTIVITY_ROWS_PER_SIGNAL]
        for follow in organizations:
            domain = follow.organization.domain
            add_activity("follows", ("organization", follow.organization_id), follow.created_at,
                         [domain.name] if domain else [], SIGNAL_WEIGHTS["follow"])

        post_likes = PostLike.objects.filter(
            user=user, post__visibility="PUBLIC",
        ).filter(
            Q(post__talent__isnull=True) | Q(post__talent__profile_visibility="PUBLIC")
        ).select_related("post__talent", "post__organization__domain").prefetch_related(
            "post__talent__domains",
            "post__talent__skills__related_skills__related_skill",
        ).order_by("-created_at")[:MAX_ACTIVITY_ROWS_PER_SIGNAL]
        for like in post_likes:
            labels = cls._candidate_topics(like.post, "FEED")
            add_activity("likes", ("post", like.post_id), like.created_at, labels, SIGNAL_WEIGHTS["like"])

        # SavedPost has no uniqueness constraint in older installations; the
        # seen key ensures a repeated row cannot multiply an inferred signal.
        saved_posts = SavedPost.objects.filter(
            user=user, post__visibility="PUBLIC",
        ).filter(
            Q(post__talent__isnull=True) | Q(post__talent__profile_visibility="PUBLIC")
        ).select_related("post__talent", "post__organization__domain").prefetch_related(
            "post__talent__domains",
            "post__talent__skills__related_skills__related_skill",
        ).order_by("-created_at")[:MAX_ACTIVITY_ROWS_PER_SIGNAL]
        for save in saved_posts:
            add_activity("saves", ("post", save.post_id), save.created_at,
                         cls._candidate_topics(save.post, "FEED"), SIGNAL_WEIGHTS["save"])

        applications = Application.objects.filter(
            talent__user=user,
        ).select_related("opportunity__domain").prefetch_related(
            "opportunity__skills",
        ).order_by("-created_at")[:MAX_ACTIVITY_ROWS_PER_SIGNAL]
        for application in applications:
            opportunity = application.opportunity
            labels = [opportunity.domain.name, *opportunity.skills.values_list("name", flat=True)]
            add_activity("applications", ("opportunity", opportunity.pk), application.created_at,
                         labels, SIGNAL_WEIGHTS["application"])

        enrollments = Enrollment.objects.filter(
            user=user, course__status="APPROVED",
        ).select_related("course__category").order_by("-enrolled_at")[:MAX_ACTIVITY_ROWS_PER_SIGNAL]
        for enrollment in enrollments:
            category = enrollment.course.category
            add_activity("enrollments", ("course", enrollment.course_id), enrollment.enrolled_at,
                         [category.name] if category else [], SIGNAL_WEIGHTS["enrollment"])

        course_likes = CourseLike.objects.filter(
            user=user, course__status="APPROVED",
        ).select_related("course__category").order_by("-created_at")[:MAX_ACTIVITY_ROWS_PER_SIGNAL]
        for like in course_likes:
            category = like.course.category
            add_activity("likes", ("course", like.course_id), like.created_at,
                         [category.name] if category else [], SIGNAL_WEIGHTS["like"])

        event_likes = EventLike.objects.filter(
            user=user,
            event__status="PUBLISHED",
            event__organizer__status="ACTIVE",
        ).select_related("event__category__domain").order_by("-created_at")[:MAX_ACTIVITY_ROWS_PER_SIGNAL]
        for like in event_likes:
            category = like.event.category
            labels = [category.name] if category else []
            if category and category.domain_id:
                labels.append(category.domain.name)
            add_activity("likes", ("event", like.event_id), like.created_at,
                         labels, SIGNAL_WEIGHTS["like"])

        results = []
        for topic, score in topic_scores.items():
            strength = min(1.0, score / 8.0)
            results.append({
                "topic": topic,
                "strength": round(strength, 4),
                "score": round(score, 4),
                "signals": sorted(topic_sources[topic]),
                "explanation": "Inferred from your recent recommendation-related activity; older activity decays and has less influence.",
            })
        results.sort(key=lambda row: (row["score"], row["topic"]), reverse=True)
        return results[:limit]

    @classmethod
    def active_topic_strengths(cls, user):
        return {row["topic"]: row["strength"] for row in cls.inferred_interests(user)}

    @classmethod
    def dismissed_item_ids(cls, user, item_kind):
        return set(RecommendationFeedback.objects.filter(
            user=user,
            item_kind=str(item_kind).upper(),
            action=RecommendationFeedback.Action.DISMISSED,
        ).values_list("item_id", flat=True))

    @classmethod
    def remove_dismissal(cls, user, item_kind, item_id):
        return RecommendationFeedback.objects.filter(
            user=user,
            item_kind=str(item_kind).upper(),
            item_id=item_id,
            action=RecommendationFeedback.Action.DISMISSED,
        ).delete()[0] > 0

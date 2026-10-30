"""Reproducible momentum signals and consent-bound matching, version 1."""
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from heapq import nlargest

from django.contrib.auth import get_user_model
from django.db import transaction
from django.conf import settings
from django.db.models import Exists, OuterRef, Prefetch, Q, prefetch_related_objects
from django.utils import timezone
from django.utils.crypto import salted_hmac

from accounts.models import UserBlock
from notifications.models import Notification
from notifications.services import create_notification
from organizations.permissions import OrganizationCapability as Cap, has_organization_capability
from organizations.models import Organization
from skills.models import Skill
from talents.models import Achievement, TalentProfile
from .ecosystems import normalize_topic
from .interest_learning import is_sensitive_topic
from .models import RisingTalentAlert, RisingTalentPreference as Preference, RisingTalentSnapshot as Snapshot

VERSION = "rising-talent-v1"
THRESHOLD = 45
WINDOW_DAYS = 90
MIN_BASELINE_DAYS = 7
MAX_DAILY_ALERTS = 5
CATEGORIES = dict(Preference.CATEGORIES)
BATCH_SIZE = 100
MAX_PUBLIC_SKILLS = 500
MAX_ACHIEVEMENTS = 500


def day_bounds(day):
    zone = timezone.get_current_timezone()
    return (timezone.make_aware(datetime.combine(day, time.min), zone),
            timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min), zone))


def alert_keys(user_id, talent_id, period):
    value = f"{user_id}:{talent_id}:{period}"
    secrets = [settings.SECRET_KEY, *getattr(settings, "SECRET_KEY_FALLBACKS", [])]
    return tuple(dict.fromkeys(salted_hmac("rising-talent-alert", value, secret=secret,
                                         algorithm="sha256").hexdigest() for secret in secrets))


def skill_prefetch():
    return Prefetch("skills", queryset=Skill.objects.only("id", "name").order_by("pk")[:MAX_PUBLIC_SKILLS + 1], to_attr="rising_skills")


def public_skills(talent):
    return talent.rising_skills if hasattr(talent, "rising_skills") else list(talent.skills.all())


def evidence_prefetches(day):
    return [skill_prefetch(),
        Prefetch("achievements", queryset=Achievement.objects.filter(
            date_received__gte=day - timedelta(days=89), date_received__lte=day
        ).only("id", "talent_id", "title", "date_received").order_by("pk")[:MAX_ACHIEVEMENTS + 1], to_attr="rising_achievements"),
        Prefetch("rising_snapshots", queryset=Snapshot.objects.filter(
            day__gte=day - timedelta(days=WINDOW_DAYS), day__lte=day - timedelta(days=MIN_BASELINE_DAYS)
        ).only("id", "talent_id", "day", "skill_topics").order_by("day", "pk")[:1], to_attr="rising_baselines")]


def keyset_batches(rows, batch_size=BATCH_SIZE, after=0):
    while True:
        batch = list(rows.filter(pk__gt=after).order_by("pk")[:batch_size])
        if not batch:
            return
        yield batch
        after = batch[-1].pk


def safe_skills(skills):
    # Aliases and duplicate labels contribute only once to the score.
    result = {}
    for skill in sorted(skills, key=lambda item: item.pk):
        key = normalize_topic(skill.name)
        if key and not is_sensitive_topic(key):
            result.setdefault(key, skill)
    return list(result.values())


def eligible_talents():
    return TalentProfile.objects.filter(user__is_active=True, user__role="ATHLETE",
        profile_visibility="PUBLIC", talent_category__in=CATEGORIES,
        user__rising_talent_preference__discovery_enabled=True)


def evidence_rows(rows, day):
    return public_candidate_rows(rows).prefetch_related(*evidence_prefetches(day))


def public_candidate_rows(rows):
    return rows.select_related("user").only("id", "user_id", "talent_category",
        "user__id", "user__username", "user__first_name", "user__last_name")


def assess(talent, day=None, *, _skills=None, _topics=None):
    """Score declared skills, dated achievements, and measured changes only."""
    day = day or timezone.localdate()
    if not hasattr(talent, "rising_achievements"):
        talent = evidence_rows(TalentProfile.objects.filter(pk=talent.pk), day).get()
    declared_skills = public_skills(talent)
    if len(declared_skills) > MAX_PUBLIC_SKILLS or len(talent.rising_achievements) > MAX_ACHIEVEMENTS:
        return {"algorithm": VERSION, "score": 0, "threshold": THRESHOLD, "qualified": False,
                "components": dict.fromkeys(("skills", "achievements", "skill_growth", "achievement_growth"), 0),
                "explanations": ["Automatic matching is paused because this profile exceeds the evidence review limit. No score was assigned."],
                "evidence_complete": False, "baseline_available": False, "as_of": day.isoformat()}
    skills = _skills if _skills is not None else safe_skills(declared_skills)
    # Repeated uploads of the same dated achievement do not create momentum.
    achievements = set()
    for row in talent.rising_achievements:
        title = normalize_topic(row.title)
        if title:
            achievements.add((title, row.date_received))
    current = sum(date >= day - timedelta(days=29) for _, date in achievements)
    previous = sum(day - timedelta(days=59) <= date < day - timedelta(days=29) for _, date in achievements)
    baseline = talent.rising_baselines[0] if talent.rising_baselines else None
    topics = set(_topics) if _topics is not None else {normalize_topic(skill.name) for skill in skills}
    added = len(topics - set(baseline.skill_topics)) if baseline else 0
    momentum = max(0, current - previous)
    components = {"skills": min(len(skills), 5) * 5,
                  "achievements": min(len(achievements), 3) * 10,
                  "skill_growth": min(added, 3) * 10,
                  "achievement_growth": min(momentum, 3) * 5}
    score = min(100, sum(components.values()))
    reasons = [f"{len(skills)} distinct public skills.",
               f"{len(achievements)} distinct dated achievements in the last 90 days (self-reported)."]
    if baseline:
        reasons.append(f"{added} new skills since the measured baseline {(day - baseline.day).days} days ago.")
    else:
        reasons.append("Skill growth needs a baseline at least 7 days old; no skill growth points were awarded.")
    reasons.append(f"{current} dated achievements in the last 30 days versus {previous} in the previous 30 days.")
    qualified = score >= THRESHOLD and len(skills) >= 2 and bool(achievements) and (added > 0 or momentum > 0)
    return {"algorithm": VERSION, "score": score, "threshold": THRESHOLD, "qualified": qualified,
            "components": components, "explanations": reasons, "baseline_available": baseline is not None,
            "as_of": day.isoformat(), "evidence_complete": True}


def recipient_profile(user, preference):
    """Resolve current authority; platform admin flags grant no access."""
    current = get_user_model().objects.filter(pk=user.pk, is_active=True).select_related(
        "coach_profile", "scout_profile").only("id", "role", "is_active",
        "coach_profile__id", "coach_profile__user_id", "scout_profile__id", "scout_profile__user_id").first()
    if not current:
        return None
    if current.role not in {"ORGANIZATION", "COACH", "SCOUT"}:
        return None
    relation = {"COACH": "coach_profile", "SCOUT": "scout_profile"}.get(current.role)
    profile = getattr(current, relation, None) if relation else None
    if relation and profile is None:
        return None
    if preference.organization_id:
        organization = Organization.objects.select_related("user").filter(pk=preference.organization_id).first()
        if organization and has_organization_capability(current, organization, Cap.VIEW_TALENTS):
            return organization
        return None
    return profile


def preference_for(user):
    return Preference.objects.select_related("organization").prefetch_related("skills").filter(user=user).first()


def matching_context(user, preference=None):
    preference = preference or preference_for(user)
    if not preference or preference.category not in CATEGORIES:
        return None
    scope = recipient_profile(user, preference)
    if scope is None:
        return None
    if isinstance(scope, Organization):
        preference.organization = scope  # Fresh owner/block scope after transfers.
    skills = safe_skills(preference.skills.all())
    return (preference, skills) if skills else None


@dataclass
class MatchContext:
    user: object
    preference: object
    topics: set
    peers: set
    principals: set


def build_context(user, preference=None):
    context = matching_context(user, preference)
    if not context:
        return None
    preference, interests = context
    peers = {user.pk}
    principals = {user.pk}
    if preference.organization_id:
        owner_id = preference.organization.user_id
        if owner_id:
            principals.add(owner_id)
    topics = {normalize_topic(skill.name) for skill in interests}
    return MatchContext(user, preference, topics, peers, principals)


def blocked_pairs(principals, targets):
    """Read only block edges relevant to this candidate page, not whole graphs."""
    rows = UserBlock.objects.filter(Q(user_id__in=principals, blocked_user_id__in=targets)
        | Q(blocked_user_id__in=principals, user_id__in=targets)).values_list("user_id", "blocked_user_id")
    result = set()
    for left, right in rows.iterator(chunk_size=BATCH_SIZE):
        if left in principals and right in targets:
            result.add((left, right))
        if right in principals and left in targets:
            result.add((right, left))
    return result


def match_row(talent, context, assessment, skills, *, topics=None):
    topics = topics if topics is not None else {normalize_topic(skill.name): skill.name for skill in skills}
    shared = sorted({topics[topic] for topic in context.topics.intersection(topics)})
    if not shared or talent.user_id in context.peers or not assessment["qualified"]:
        return None
    return {"talent_id": talent.pk, "name": talent.user.get_full_name() or talent.user.username,
            "category": talent.talent_category, "category_name": CATEGORIES[talent.talent_category],
            "assessment": assessment, "matched_skills": shared,
            "match_explanation": f"Matches your {CATEGORIES[context.preference.category]} focus and skills: {', '.join(shared)}."}


def candidate_matches(contexts, day, batch_size=BATCH_SIZE):
    """Score once per candidate per bounded recipient group, without catalog scans."""
    by_topic = defaultdict(set)
    for key, context in contexts.items():
        for topic in context.topics:
            by_topic[(context.preference.category, topic)].add(key)
    if not by_topic:
        return
    rows = eligible_talents().filter(talent_category__in={key[0] for key in by_topic})
    rows = public_candidate_rows(rows).prefetch_related(skill_prefetch())
    principals = set().union(*(context.principals for context in contexts.values()))
    for batch in keyset_batches(rows, batch_size):
        blocked = blocked_pairs(principals, {talent.user_id for talent in batch})
        relevant = []
        for talent in batch:
            skills = safe_skills(public_skills(talent))
            topics = {normalize_topic(skill.name): skill.name for skill in skills}
            targets = set()
            for topic in topics:
                targets.update(by_topic.get((talent.talent_category, topic), ()))
            targets = {key for key in targets if talent.user_id not in contexts[key].peers
                       and not any((actor, talent.user_id) in blocked for actor in contexts[key].principals)}
            if targets:
                relevant.append((talent, skills, targets, topics))
        prefetch_related_objects([talent for talent, _, _, _ in relevant], *evidence_prefetches(day))
        for talent, skills, targets, topics in relevant:
            assessment = assess(talent, day, _skills=skills, _topics=topics)
            if assessment["qualified"]:
                for key in targets:
                    row = match_row(talent, contexts[key], assessment, skills, topics=topics)
                    if row:
                        yield key, row


def matches_for(user, *, limit=50, day=None, preference=None):
    day = day or timezone.localdate()
    context = build_context(user, preference)
    if context is None:
        return []
    return nlargest(min(max(limit, 1), 50), (row for _, row in candidate_matches({user.pk: context}, day)),
                    key=lambda row: (row["assessment"]["score"], -row["talent_id"]))


def match_for_talent(user, talent_id, day=None, preference=None):
    """Fresh, single-candidate privacy check for creation and delivery."""
    day = day or timezone.localdate()
    context = build_context(user, preference)
    if context is None:
        return None
    blocks = UserBlock.objects.filter(Q(user_id__in=context.principals, blocked_user_id=OuterRef("user_id"))
        | Q(blocked_user_id__in=context.principals, user_id=OuterRef("user_id")))
    rows = eligible_talents().filter(pk=talent_id, talent_category=context.preference.category).exclude(
        user_id__in=context.peers).filter(~Exists(blocks))
    talent = evidence_rows(rows, day).first()
    if talent is None:
        return None
    return match_row(talent, context, assess(talent, day), safe_skills(public_skills(talent)))


def erase_alert_links(rows, *, delete_receipts=False, batch_size=BATCH_SIZE):
    """Bound Django's deletion collector as well as the SELECT result size."""
    for batch in keyset_batches(rows.only("id", "notification_id"), batch_size):
        ids = [row.pk for row in batch]
        with transaction.atomic():
            Notification.objects.filter(pk__in=[row.notification_id for row in batch if row.notification_id]).delete()
            target = RisingTalentAlert.objects.filter(pk__in=ids)
            if delete_receipts:
                target.delete()
            else:
                target.update(talent=None)


def purge_talent(talent_id):
    # Opaque receipts retain rate limits without the talent association.
    erase_alert_links(RisingTalentAlert.objects.filter(talent_id=talent_id))
    Snapshot.objects.filter(talent_id=talent_id).delete()


@transaction.atomic
def set_preferences(user, values):
    # Serialize changes with alert creation and never accept another user's ID.
    values = dict(values)
    preference, _ = Preference.objects.get_or_create(user=user)
    preference = Preference.objects.select_for_update().get(pk=preference.pk)
    skills = values.pop("skills", None)
    for key, value in values.items():
        setattr(preference, key, value)
    preference.save()
    if skills is not None:
        preference.skills.set(skills)
    if not preference.discovery_enabled:
        for talent_id in TalentProfile.objects.filter(user=user).values_list("pk", flat=True):
            purge_talent(talent_id)
    if not preference.alerts_enabled:
        erase_alert_links(RisingTalentAlert.objects.filter(recipient=user))
    return preference


def record_snapshots(day=None, batch_size=BATCH_SIZE):
    day = day or timezone.localdate()
    cutoff, _ = day_bounds(day - timedelta(days=WINDOW_DAYS))
    for batch in keyset_batches(Snapshot.objects.filter(day__lt=day - timedelta(days=WINDOW_DAYS)).only("pk"), batch_size):
        Snapshot.objects.filter(pk__in=[row.pk for row in batch]).delete()
    erase_alert_links(RisingTalentAlert.objects.filter(created_at__lt=cutoff), delete_receipts=True, batch_size=batch_size)
    ineligible = TalentProfile.objects.exclude(pk__in=eligible_talents()).filter(
        Exists(RisingTalentAlert.objects.filter(talent_id=OuterRef("pk")))
        | Exists(Snapshot.objects.filter(talent_id=OuterRef("pk"))))
    for batch in keyset_batches(ineligible.only("pk", "user_id"), batch_size):
        with transaction.atomic():
            list(Preference.objects.select_for_update().filter(user_id__in=[row.user_id for row in batch]).order_by("user_id"))
            for talent in batch:
                if not eligible_talents().filter(pk=talent.pk).exists():
                    purge_talent(talent.pk)
    count = 0
    missing = eligible_talents().exclude(rising_snapshots__day=day).only("pk", "user_id")
    for batch in keyset_batches(missing, batch_size):
        with transaction.atomic():
            # Prefetch only AFTER locks; observations read before a concurrent
            # withdrawal/re-enrolment must never become the new baseline.
            list(Preference.objects.select_for_update().filter(user_id__in=[row.user_id for row in batch]).order_by("user_id"))
            current = eligible_talents().filter(pk__in=[row.pk for row in batch]).exclude(
                rising_snapshots__day=day).only("id", "user_id").prefetch_related(skill_prefetch())
            snapshots = [Snapshot(talent=talent, day=day,
                skill_topics=[normalize_topic(skill.name) for skill in safe_skills(public_skills(talent))])
                for talent in current if len(public_skills(talent)) <= MAX_PUBLIC_SKILLS]
            Snapshot.objects.bulk_create(snapshots, ignore_conflicts=True, batch_size=batch_size)
            count += len(snapshots)
    return count


@transaction.atomic
def notify_match(user, talent_id, day=None):
    day = day or timezone.localdate()
    # Lock consent rows in a stable order before rechecking privacy and relevance.
    candidate_user_id = TalentProfile.objects.filter(pk=talent_id).values_list("user_id", flat=True).first()
    list(Preference.objects.select_for_update().filter(user_id__in=[user.pk, candidate_user_id]).order_by("user_id"))
    preference = preference_for(user)
    if not preference or not preference.alerts_enabled:
        return False
    start, end = day_bounds(day)
    if RisingTalentAlert.objects.filter(recipient=user, created_at__gte=start, created_at__lt=end).count() >= MAX_DAILY_ALERTS:
        return False
    period = day - timedelta(days=day.weekday())
    keys = alert_keys(user.pk, talent_id, period)
    if RisingTalentAlert.objects.filter(Q(deduplication_key__in=keys)
            | Q(recipient=user, talent_id=talent_id, period=period)).exists():
        return False
    if match_for_talent(user, talent_id, day=day, preference=preference) is None:
        return False
    key = keys[0]
    alert, created = RisingTalentAlert.objects.get_or_create(deduplication_key=key,
        defaults={"recipient": user, "talent_id": talent_id, "period": period})
    if not created:
        return False
    notification = create_notification(user=user, notification_type="AI_MATCH",
        message="A rising talent matches your selected category and skills. Review the evidence in Rising Talent.",
        metadata={"feature": "rising_talent"}, deduplication_key=f"rising:{key}")
    alert.notification = notification
    alert.save(update_fields=["notification"])
    return True


def notification_is_current(notification):
    if not isinstance(notification.metadata, dict) or notification.metadata.get("feature") != "rising_talent":
        return True
    alert = RisingTalentAlert.objects.filter(notification=notification, recipient=notification.user).first()
    preference = preference_for(notification.user)
    return bool(alert and alert.talent_id and preference and preference.alerts_enabled
                and match_for_talent(notification.user, alert.talent_id, preference=preference))

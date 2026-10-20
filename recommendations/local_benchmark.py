"""Local fixture manifest and black-box benchmarks; never used by app requests.

Relevance labels and eligibility exclusions are authored while seeding, without
consulting recommendation scores or filtering the engine's returned candidates.
"""
from dataclasses import dataclass, field
from datetime import timedelta
from math import ceil
from time import perf_counter

from django.contrib.auth import get_user_model
from django.core.management.base import CommandError
from django.test.utils import override_settings
from django.utils import timezone

from applications.models import Application
from domains.models import TalentDomain
from learning.models import Course, Enrollment, LearningCategory
from opportunities.models import Opportunity
from organizations.models import Organization, OrganizationCategory, OrganizationDomain
from recommendations.services import RecommendationEngine
from recommendations.unified import UnifiedRecommendationService
from skills.models import Skill
from talents.models import TalentProfile


SURFACES = ("talents", "opportunities", "courses", "organizations")
FIXTURE_PREFIX = "Fictional recommendation sandbox"


@dataclass
class CandidateLabel:
    cohort: int
    eligible: bool = True
    excluded_users: set = field(default_factory=set)


@dataclass
class FixtureManifest:
    segments: dict = field(default_factory=dict)
    user_cohorts: dict = field(default_factory=dict)
    catalogs: dict = field(default_factory=lambda: {surface: {} for surface in SURFACES})


def seed_extended_fixtures(users, groups, username_prefix):
    """Called inside the guarded seed command's atomic transaction.

    Keep the original 90 users, adding nine cold-start users and nine labeled
    catalogs. Every catalog has seven eligible items per cohort plus distractors.
    """
    manifest = FixtureManifest(segments={"profiled": users})
    for user in users:
        cohort = (int(user.username.removeprefix(username_prefix)) - 1) // 10
        manifest.user_cohorts[user.pk] = cohort
        manifest.catalogs["talents"][user.talent_profile.pk] = CandidateLabel(
            cohort, excluded_users={user.pk},
        )

    for variant in ("no_profile", "empty_profile", "profile_only"):
        cold_users = []
        for cohort in (0, 3, 6):
            username = f"{username_prefix}cold_{variant}_{cohort}"
            email = f"{username}@example.invalid"
            user, created = get_user_model().objects.get_or_create(
                username=username, defaults={"email": email, "first_name": "Fictional cold start"},
            )
            if not created and (user.email != email or user.has_usable_password()
                                or user.is_staff or user.is_superuser):
                raise CommandError(f"Refusing to modify conflicting account: {username}")
            if created:
                user.set_unusable_password()
                user.save(update_fields=["password"])
            if variant == "no_profile":
                if TalentProfile.objects.filter(user=user).exists():
                    raise CommandError(f"No-profile fixture already has a profile: {username}")
            else:
                category, topic, skill_name = groups[cohort]
                profile, _ = TalentProfile.objects.update_or_create(user=user, defaults={
                    "talent_category": category if variant == "profile_only" else None,
                    "talent_area": topic if variant == "profile_only" else "",
                    "headline": "", "biography": "", "country": "", "city": "",
                    "profile_visibility": "PUBLIC", "experience_level": "BEGINNER",
                })
                profile.domains.set([TalentDomain.objects.get(name=topic)] if variant == "profile_only" else [])
                profile.skills.set([Skill.objects.get(
                    category__name=FIXTURE_PREFIX, name=skill_name,
                )] if variant == "profile_only" else [])
                manifest.catalogs["talents"][profile.pk] = CandidateLabel(
                    cohort, excluded_users={user.pk},
                )
            cold_users.append(user)
            manifest.user_cohorts[user.pk] = cohort
        manifest.segments[f"cold_{variant}"] = cold_users

    today = timezone.localdate()
    for cohort, (talent_category, topic, skill_name) in enumerate(groups):
        members = [user for user in users if manifest.user_cohorts[user.pk] == cohort]
        domain = TalentDomain.objects.get(name=topic)
        skill = Skill.objects.get(category__name=FIXTURE_PREFIX, name=skill_name)
        category_name = {
            "SPORTS": "Sports", "SCIENCE_TECHNOLOGY": "Technology", "ARTS": "Arts",
            "OTHERS": "Other talents",
        }[talent_category]
        org_category, _ = OrganizationCategory.objects.get_or_create(name=category_name)
        org_domain, _ = OrganizationDomain.objects.get_or_create(category=org_category, name=topic)
        learning_category, _ = LearningCategory.objects.get_or_create(name=topic)
        organizations = []
        for slot in range(8):
            closed = slot == 7
            organization, _ = Organization.objects.update_or_create(
                name=f"{FIXTURE_PREFIX} {cohort:02d} organization {slot:02d}",
                defaults={"category": org_category, "domain": org_domain, "country": "Ghana",
                          "description": f"Synthetic {topic} organization.",
                          "status": "CLOSED" if closed else "ACTIVE",
                          "official": False, "verified": closed},
            )
            organizations.append(organization)
            manifest.catalogs["organizations"][organization.pk] = CandidateLabel(cohort, not closed)

        for slot in range(10):
            # Slots 7/8/9 are inactive, expired, and attached to a closed org.
            opportunity, _ = Opportunity.objects.update_or_create(
                title=f"{FIXTURE_PREFIX} {cohort:02d} opportunity {slot:02d}",
                defaults={"organization": organizations[slot if slot < 7 else (7 if slot == 9 else 0)],
                          "domain": domain, "description": f"Practice {topic} and {skill_name}.",
                          "active": slot != 7,
                          "deadline": today - timedelta(days=1) if slot == 8 else today + timedelta(days=30),
                          "experience_level": "BEGINNER", "work_type": "REMOTE", "location": ""},
            )
            opportunity.skills.set([skill])
            excluded_users = set()
            if slot == 0:
                Application.objects.get_or_create(talent=members[0].talent_profile, opportunity=opportunity)
                excluded_users.add(members[0].pk)
            manifest.catalogs["opportunities"][opportunity.pk] = CandidateLabel(
                cohort, slot < 7, excluded_users,
            )

            creator = members[slot % len(members)]
            course, _ = Course.objects.update_or_create(
                slug=f"fictional-rec-{cohort:02d}-course-{slot:02d}",
                defaults={"creator": creator, "category": learning_category,
                          "title": f"{FIXTURE_PREFIX} {topic} course {slot:02d}",
                          "description": f"Learn {skill_name} through {topic} practice.",
                          "status": "APPROVED" if slot < 7 else ("DRAFT", "PENDING", "REJECTED")[slot - 7],
                          "level": "BEGINNER", "is_free": True},
            )
            excluded_users = {creator.pk}
            if slot == 1:
                Enrollment.objects.get_or_create(user=members[0], course=course)
                excluded_users.add(members[0].pk)
            manifest.catalogs["courses"][course.pk] = CandidateLabel(cohort, slot < 7, excluded_users)
    return manifest


def recommendations_for(user, surface, pipeline, limit=5):
    """Call actual public recommendation methods without benchmark-side filtering."""
    if surface not in SURFACES or pipeline not in ("legacy", "unified"):
        raise ValueError("Unknown recommendation surface or pipeline")
    if surface == "organizations":
        # There is no organization adapter in UnifiedRecommendationService.
        rows = RecommendationEngine.recommend_organizations_for_user(user, limit=limit)
        return [row["organization"] for row in rows]
    if pipeline == "unified":
        service = UnifiedRecommendationService()
        method = {"talents": service.recommend_talents,
                  "opportunities": service.recommend_opportunities,
                  "courses": service.recommend_learning}[surface]
        return [row["item"] for row in method(user, limit=limit)]
    engine = RecommendationEngine()
    talent = getattr(user, "talent_profile", None)
    if surface == "talents":
        return [row["talent"] for row in engine.recommend_talents_for_talent(talent, limit=limit)]
    if surface == "opportunities":
        return [row["opportunity"] for row in engine.recommend_opportunities_for_user(user, limit=limit)]
    return [row["course"] for row in engine.recommend_courses_for_talent(talent, limit=limit)]


def summarize_results(observations, catalog, user_cohorts, limit=5):
    """Score distinct, eligible, relevant IDs; unknown/duplicate IDs cannot earn hits."""
    hits = topics = returned = covered = eligible_returned = possible = 0
    latencies = []
    for user_id, candidate_ids, latency in observations:
        relevant_ids = {
            pk for pk, label in catalog.items()
            if label.cohort == user_cohorts[user_id] and label.eligible
            and user_id not in label.excluded_users
        }
        possible += len(relevant_ids)
        covered += bool(candidate_ids)
        returned += len(candidate_ids)
        seen = set()
        for pk in candidate_ids:
            label = catalog.get(pk)
            if label is not None and pk not in seen:
                topics += label.cohort == user_cohorts[user_id]
                eligible_returned += label.eligible and user_id not in label.excluded_users
                hits += pk in relevant_ids
            seen.add(pk)
        latencies.append(latency)
    users = len(observations)
    percent = lambda value, total: round(100 * value / total, 2) if total else None
    return {
        "users": users, "relevant_results": hits, "returned_results": returned,
        "eligible_relevant_candidates": possible,
        "precision_at_5_percent": percent(hits, returned),
        "topic_precision_at_5_percent": percent(topics, returned),
        "eligible_result_percent": percent(eligible_returned, returned),
        "slot_relevance_at_5_percent": percent(hits, users * limit),
        "user_coverage_percent": percent(covered, users),
        "recall_at_5_percent": percent(hits, possible),
        "mean_latency_ms": round(sum(latencies) / users, 2) if users else None,
        "p95_latency_ms": round(sorted(latencies)[ceil(users * .95) - 1], 2) if users else None,
    }


def benchmark_surface(manifest, pipeline, surface, segment, progress=None):
    observations = []
    users = manifest.segments[segment]
    # Interest inference is explicitly off: these fixtures test profile/history
    # absence, not a trained activity model. Each call gets a fresh service.
    with override_settings(UNIFIED_RECOMMENDATIONS_ENABLED=pipeline == "unified",
                           RECOMMENDATION_INTEREST_LEARNING_ENABLED=False):
        for index, user in enumerate(users, 1):
            start = perf_counter()
            candidates = recommendations_for(user, surface, pipeline)
            elapsed = (perf_counter() - start) * 1000
            observations.append((user.pk, [candidate.pk for candidate in candidates], elapsed))
            if progress and index % 10 == 0:
                progress(f"{pipeline}/{surface}/{segment}: {index}/{len(users)} users")
    return {
        "pipeline": pipeline, "surface": surface, "segment": segment,
        "backend": "shared_legacy_no_unified_adapter" if surface == "organizations" else pipeline,
        "ground_truth": "held_out_cohort" if segment in ("cold_no_profile", "cold_empty_profile") else "explicit_cohort",
        **summarize_results(observations, manifest.catalogs[surface], manifest.user_cohorts),
    }

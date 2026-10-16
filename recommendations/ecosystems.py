import re
import unicodedata
from decimal import Decimal

from django.db.models import Q

from talents.models import TalentProfile
from coaches.models import CoachProfile
from scouts.models import ScoutProfile
from organizations.models import Organization
from skills.models import Skill, SkillRelationship


CATEGORY_ALIASES = {
    "SPORTS": {"sport", "sports"},
    "SCIENCE_TECHNOLOGY": {
        "science",
        "science & technology",
        "science and technology",
        "technology",
        "science & tech",
    },
    "ARTS": {"art", "arts"},
    "OTHERS": {"other", "others"},
}

# These are true spelling/name variants. Conceptually related topics belong in
# SkillRelationship so their direction and strength remain data driven.
TOPIC_ALIASES = {
    "science technology": {
        "science and technology", "science tech", "science & tech", "technology",
    },
    "artificial intelligence": {"ai"},
    "machine learning": {"ml"},
    "soccer": {"association football", "football (soccer)"},
    "basketball": {"b-ball", "hoops"},
    "track and field": {"track & field", "athletics track and field"},
    "user experience": {"ux"},
    "user interface": {"ui"},
}
MIN_RELATED_SKILL_STRENGTH = Decimal("0.35")


def normalize_topic(value):
    """Normalize a topic label and map known aliases to a canonical label."""
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    normalized = normalized.replace("&", " and ")
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    normalized = " ".join(normalized.split())
    aliases = {
        _normalize_variant(alias): canonical
        for canonical, values in TOPIC_ALIASES.items()
        for alias in values
    }
    return aliases.get(normalized, normalized)


def _normalize(value):
    """Compatibility normalization for the existing ecosystem feed helpers."""
    return " ".join((value or "").casefold().split())


def _topic_variants(topic):
    variants = {topic}
    for canonical, aliases in TOPIC_ALIASES.items():
        canonical_normalized = normalize_topic(canonical)
        if canonical_normalized == topic:
            variants.update(_normalize_variant(alias) for alias in aliases)
    return {variant for variant in variants if variant}


def _normalize_variant(value):
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    normalized = normalized.replace("&", " and ")
    return " ".join(re.sub(r"[^\w]+", " ", normalized).split())


def _split_interest(value):
    """Keep explicit phrases; split profile interest lists on common delimiters."""
    return [
        part.strip()
        for part in re.split(r"[,;|\n]+", value or "")
        if part.strip() and len(part.strip()) <= 100
    ]


def _organization_category(category_name):
    normalized_name = _normalize(category_name)
    for category, aliases in CATEGORY_ALIASES.items():
        if normalized_name in aliases:
            return category
    return None


def _talent_details(profile):
    details = {
        _normalize(profile.talent_area),
        *(
            _normalize(name)
            for name in (
                domain.name for domain in profile.domains.all()
            )
        ),
    }

    sports_profile = getattr(profile, "sports_profile", None)
    if sports_profile:
        if sports_profile.sport:
            details.add(_normalize(sports_profile.sport.name))

    specialty_profile_names = {
        "SCIENCE_TECHNOLOGY": ("science_technology_profile",),
        "ARTS": ("arts_profile",),
        "OTHERS": ("other_profile",),
    }.get(profile.talent_category, ())
    for profile_name in specialty_profile_names:
        specialty_profile = getattr(profile, profile_name, None)
        if specialty_profile:
            for field_name in ("specialization", "discipline", "field"):
                details.add(_normalize(getattr(specialty_profile, field_name, "")))

    return {detail for detail in details if detail}


def _coach_details(profile):
    details = {_normalize(profile.specialization)}
    if profile.sport:
        details.add(_normalize(profile.sport.name))
    return {detail for detail in details if detail}


def _scout_details(profile):
    return {
        detail
        for detail in (_normalize(profile.specialization),)
        if detail
    }


def _organization_details(organization):
    details = set()
    if organization.domain:
        details.add(_normalize(organization.domain.name))
    sports_profile = getattr(organization, "sports_profile", None)
    if sports_profile:
        details.add(_normalize(sports_profile.sport.name))
    return {detail for detail in details if detail}


def _details_filter(details, fields):
    condition = Q()
    for detail in details:
        for field in fields:
            condition |= Q(**{f"{field}__iexact": detail})
    return condition


def get_ecosystem_details(user):
    """Return the viewer's broad category and exact discipline/domain labels."""
    if not user or not user.is_authenticated:
        return None, set()

    category = None
    details = set()

    talent = getattr(user, "talent_profile", None)
    coach = getattr(user, "coach_profile", None)
    scout = getattr(user, "scout_profile", None)
    organization = getattr(user, "organization_profile", None)

    if user.role == "ATHLETE" and talent:
        category = talent.talent_category
        details = _talent_details(talent)
    elif user.role == "COACH" and coach:
        category = coach.coach_category
        details = _coach_details(coach)
    elif user.role == "SCOUT" and scout:
        category = scout.scout_category
        details = _scout_details(scout)
    elif user.role == "ORGANIZATION" and organization:
        category = _organization_category(
            organization.category.name if organization.category else ""
        )
        details = _organization_details(organization)

    return category, details


def get_ecosystem_user_ids(user):
    """Find users sharing the user's category and a specific discipline/domain."""
    category, details = get_ecosystem_details(user)

    if not user or not user.is_authenticated:
        return set()
    if not category:
        return {user.pk}

    matching_user_ids = {user.pk}

    organization_categories = CATEGORY_ALIASES.get(category, set())
    organization_category_filter = Q()
    for category_name in organization_categories:
        organization_category_filter |= Q(
            category__name__iexact=category_name
        )

    talent_profiles = TalentProfile.objects.filter(
        talent_category=category,
        user__role="ATHLETE",
    )
    coach_profiles = CoachProfile.objects.filter(
        coach_category=category,
        user__role="COACH",
    )
    scout_profiles = ScoutProfile.objects.filter(
        scout_category=category,
        user__role="SCOUT",
    )
    organizations = Organization.objects.filter(
        organization_category_filter,
        user__isnull=False,
        user__role="ORGANIZATION",
    )

    if details:
        talent_profiles = talent_profiles.filter(
            _details_filter(
                details,
                (
                    "talent_area",
                    "domains__name",
                    "sports_profile__sport__name",
                    "science_technology_profile__specialization",
                    "arts_profile__specialization",
                    "arts_profile__discipline",
                    "other_profile__specialization",
                    "other_profile__field",
                ),
            )
        )
        coach_profiles = coach_profiles.filter(
            _details_filter(details, ("specialization", "sport__name"))
        )
        scout_profiles = scout_profiles.filter(
            _details_filter(details, ("specialization",))
        )
        organizations = organizations.filter(
            _details_filter(
                details,
                ("domain__name", "sports_profile__sport__name"),
            )
        )

    matching_user_ids.update(
        talent_profiles.values_list("user_id", flat=True)
    )
    matching_user_ids.update(
        coach_profiles.values_list("user_id", flat=True)
    )
    matching_user_ids.update(
        scout_profiles.values_list("user_id", flat=True)
    )
    matching_user_ids.update(
        organizations.values_list("user_id", flat=True)
    )

    return matching_user_ids


def _add_profile_value(topics, value):
    for phrase in _split_interest(value):
        topic = normalize_topic(phrase)
        if topic:
            topics.add(topic)


def _talent_profile_topics(profile):
    topics = set()
    _add_profile_value(topics, profile.talent_area)
    for domain in profile.domains.all():
        _add_profile_value(topics, domain.name)
    for skill in profile.skills.all():
        _add_profile_value(topics, skill.name)

    sports_profile = getattr(profile, "sports_profile", None)
    if sports_profile:
        if sports_profile.sport:
            _add_profile_value(topics, sports_profile.sport.name)
        if sports_profile.sport_category:
            _add_profile_value(topics, sports_profile.sport_category.name)
        _add_profile_value(topics, sports_profile.position)

    specialty_names = {
        "SCIENCE_TECHNOLOGY": ("science_technology_profile",),
        "ARTS": ("arts_profile",),
        "OTHERS": ("other_profile",),
    }.get(profile.talent_category, ())
    for profile_name in specialty_names:
        specialty = getattr(profile, profile_name, None)
        if not specialty:
            continue
        for field_name in (
            "specialization", "discipline", "field", "research_interests",
            "creative_interests", "interests",
        ):
            _add_profile_value(topics, getattr(specialty, field_name, ""))
    return topics


def _profile_topics(profile, member_type):
    if member_type == "Talent":
        return _talent_profile_topics(profile)
    topics = set()
    if member_type == "Coach":
        _add_profile_value(topics, profile.specialization)
        if profile.sport:
            _add_profile_value(topics, profile.sport.name)
    elif member_type == "Scout":
        _add_profile_value(topics, profile.specialization)
    else:
        if profile.domain:
            _add_profile_value(topics, profile.domain.name)
        sports_profile = getattr(profile, "sports_profile", None)
        if sports_profile and sports_profile.sport:
            _add_profile_value(topics, sports_profile.sport.name)
    return topics


def _public_related_profile_filter(viewer_id):
    """Honor talent visibility when a user has more than one profile type."""
    return (
        Q(user_id=viewer_id)
        | Q(user__talent_profile__isnull=True)
        | Q(user__talent_profile__profile_visibility="PUBLIC")
    )


def _matching_profile_user_ids(topics):
    """Use topic text and skill IDs to query only profiles near viewer topics."""
    terms = set()
    for topic in topics:
        terms.update(_topic_variants(topic))
    if not terms:
        return set()

    def text_filter(fields):
        condition = Q(pk__in=[])
        for field in fields:
            for term in terms:
                condition |= Q(**{f"{field}__icontains": term})
        return condition

    talent_fields = (
        "talent_area", "domains__name",
        "sports_profile__sport__name", "sports_profile__sport_category__name",
        "sports_profile__position", "science_technology_profile__specialization",
        "science_technology_profile__research_interests",
        "arts_profile__specialization", "arts_profile__discipline",
        "arts_profile__creative_interests", "other_profile__specialization",
        "other_profile__field", "other_profile__interests",
    )
    matching_skill_ids = set()
    for term in terms:
        matching_skill_ids.update(Skill.objects.filter(
            name__icontains=term,
        ).values_list("id", flat=True))
    related_skill_filter = Q(pk__in=[])
    for term in terms:
        related_skill_filter |= Q(related_skill__name__iexact=term)
    matching_skill_ids.update(SkillRelationship.objects.filter(
        related_skill_filter,
        strength__gte=MIN_RELATED_SKILL_STRENGTH,
    ).values_list("skill_id", flat=True))
    talent_filter = text_filter(talent_fields)
    if matching_skill_ids:
        talent_filter |= Q(skills__id__in=matching_skill_ids)
    matching_ids = set(TalentProfile.objects.filter(
        user__is_active=True,
    ).filter(talent_filter).values_list("user_id", flat=True))
    matching_ids.update(CoachProfile.objects.filter(
        user__is_active=True,
    ).filter(text_filter(("specialization", "sport__name"))).values_list("user_id", flat=True))
    matching_ids.update(ScoutProfile.objects.filter(
        user__is_active=True,
    ).filter(text_filter(("specialization",))).values_list("user_id", flat=True))
    matching_ids.update(Organization.objects.filter(
        user__isnull=False,
        user__is_active=True,
        status="ACTIVE",
    ).filter(text_filter(("domain__name", "sports_profile__sport__name"))).values_list("user_id", flat=True))
    return matching_ids


def _viewer_profile(user):
    profile_by_role = {
        "ATHLETE": "talent_profile",
        "COACH": "coach_profile",
        "SCOUT": "scout_profile",
        "ORGANIZATION": "organization_profile",
    }
    profile_name = profile_by_role.get(getattr(user, "role", None))
    profile = getattr(user, profile_name, None) if profile_name else None
    if profile is not None:
        return profile
    for profile_name in profile_by_role.values():
        profile = getattr(user, profile_name, None)
        if profile is not None:
            return profile
    return None


def _profile_type(user):
    profile = _viewer_profile(user)
    if isinstance(profile, TalentProfile):
        return "Talent"
    if isinstance(profile, CoachProfile):
        return "Coach"
    if isinstance(profile, ScoutProfile):
        return "Scout"
    return "Organization" if profile is not None else ""


def _ecosystem_profiles(user_ids, viewer_id):
    """Load active, discoverable cross-role profiles and their normalized topics."""
    profiles = []
    public_user = _public_related_profile_filter(viewer_id)

    talents = TalentProfile.objects.filter(
        user_id__in=user_ids,
        user__is_active=True,
    ).filter(
        Q(user_id=viewer_id) | Q(profile_visibility="PUBLIC")
    ).select_related(
        "user", "sports_profile__sport", "sports_profile__sport_category",
        "science_technology_profile", "arts_profile", "other_profile",
    ).prefetch_related("domains", "skills")
    talent_profiles = list(talents)
    skill_ids = {skill.pk for profile in talent_profiles for skill in profile.skills.all()}
    related_topics = {}
    if skill_ids:
        for relationship in SkillRelationship.objects.filter(
            skill_id__in=skill_ids,
            strength__gte=MIN_RELATED_SKILL_STRENGTH,
        ).select_related("related_skill"):
            weight = max(0.0, min(float(relationship.strength), 1.0))
            related_topics.setdefault(relationship.skill_id, []).append(
                (normalize_topic(relationship.related_skill.name), weight)
            )

    for profile in talent_profiles:
        topics = _talent_profile_topics(profile)
        for skill in profile.skills.all():
            for topic, _weight in related_topics.get(skill.pk, ()):
                if topic:
                    topics.add(topic)
        profiles.append((profile.user, profile, topics, "Talent"))

    coaches = CoachProfile.objects.filter(
        user_id__in=user_ids,
        user__is_active=True,
    ).filter(public_user).select_related("user", "sport")
    for profile in coaches:
        profiles.append((profile.user, profile, _profile_topics(profile, "Coach"), "Coach"))

    scouts = ScoutProfile.objects.filter(
        user_id__in=user_ids,
        user__is_active=True,
    ).filter(public_user).select_related("user")
    for profile in scouts:
        profiles.append((profile.user, profile, _profile_topics(profile, "Scout"), "Scout"))

    organizations = Organization.objects.filter(
        user_id__in=user_ids,
        user__is_active=True,
        status="ACTIVE",
    ).filter(public_user).select_related(
        "user", "category", "domain", "sports_profile__sport",
    )
    for profile in organizations:
        profiles.append((profile.user, profile, _profile_topics(profile, "Organization"), "Organization"))

    return profiles


def recommend_sub_ecosystems(user, limit=6, minimum_members=2):
    """Build ranked, overlapping specialty groups inside the user's ecosystem.

    A user can belong to several sub-ecosystems when their profile spans several
    disciplines. Groups are computed from current profiles, so updates to an
    existing ecosystem are reflected without a separate synchronization job.
    """
    if (
        not user
        or not getattr(user, "is_authenticated", False)
        or limit <= 0
        or minimum_members < 2
    ):
        return []

    viewer_profile = _viewer_profile(user)
    if viewer_profile is None:
        return []
    viewer_topics = _profile_topics(viewer_profile, _profile_type(user))
    direct_viewer_topics = set(viewer_topics)
    viewer_skill_ids = set(viewer_profile.skills.values_list("id", flat=True)) if isinstance(viewer_profile, TalentProfile) else set()
    viewer_related = {}
    if viewer_skill_ids:
        for relationship in SkillRelationship.objects.filter(
            skill_id__in=viewer_skill_ids,
            strength__gte=MIN_RELATED_SKILL_STRENGTH,
        ).select_related("related_skill"):
            topic = normalize_topic(relationship.related_skill.name)
            if topic:
                viewer_related[topic] = max(
                    viewer_related.get(topic, 0.0),
                    max(0.0, min(float(relationship.strength), 1.0)),
                )
    viewer_topics.update(viewer_related)
    if not viewer_topics:
        return []

    candidate_ids = _matching_profile_user_ids(viewer_topics) | {user.pk}
    focus_groups = {}
    for member, profile, topics, member_type in _ecosystem_profiles(candidate_ids, user.pk):
        for topic in topics & viewer_topics:
            group = focus_groups.setdefault(topic, {})
            group[member.pk] = {"user": member, "profile": profile, "type": member_type}

    recommendations = []
    for focus, members_by_id in focus_groups.items():
        if len(members_by_id) < minimum_members:
            continue

        member_types = sorted({
            item["type"] for item in members_by_id.values()
        })
        viewer_is_member = user.pk in members_by_id
        score = min(
            100,
            30
            + min(len(members_by_id), 10) * 5
            + min(len(member_types) - 1, 3) * 7
            + (
                12 if focus in direct_viewer_topics
                else round(12 * viewer_related.get(focus, 0.0))
            ),
        )
        recommendations.append({
            "name": focus.title(),
            "focus": focus,
            "member_count": len(members_by_id),
            "member_types": member_types,
            "score": score,
            "viewer_is_member": viewer_is_member,
            "reason": (
                f"{len(members_by_id)} active, discoverable members share {focus.title()}"
                + (
                    f", a related interest (strength {viewer_related[focus]:.2f})"
                    if focus in viewer_related and focus not in direct_viewer_topics
                    else ""
                )
                + (
                    " across " + ", ".join(member_types)
                    if len(member_types) > 1
                    else ""
                )
                + "."
            ),
        })

    recommendations.sort(
        key=lambda item: (
            item["score"],
            item["member_count"],
            item["focus"],
        ),
        reverse=True,
    )
    return recommendations[:limit]

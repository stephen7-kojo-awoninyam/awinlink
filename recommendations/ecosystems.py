from talents.models import TalentProfile
from coaches.models import CoachProfile
from scouts.models import ScoutProfile
from organizations.models import Organization
from django.db.models import Q


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


def _normalize(value):
    return " ".join((value or "").casefold().split())


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


def _ecosystem_profiles(user_ids, viewer_id):
    """Load public, active profiles in the existing ecosystem with their focus tags."""
    profiles = []

    talents = TalentProfile.objects.filter(
        user_id__in=user_ids,
        user__is_active=True,
    ).filter(
        Q(user_id=viewer_id) | Q(profile_visibility="PUBLIC")
    ).select_related(
        "user",
        "sports_profile__sport",
        "science_technology_profile",
        "arts_profile",
        "other_profile",
    ).prefetch_related("domains", "skills")
    for profile in talents:
        focus_tags = _talent_details(profile) | {
            _normalize(skill.name) for skill in profile.skills.all() if skill.name
        }
        profiles.append((profile.user, profile, focus_tags, "Talent"))

    coaches = CoachProfile.objects.filter(
        user_id__in=user_ids,
        user__is_active=True,
    ).select_related("user", "sport")
    for profile in coaches:
        profiles.append((profile.user, profile, _coach_details(profile), "Coach"))

    scouts = ScoutProfile.objects.filter(
        user_id__in=user_ids,
        user__is_active=True,
    ).select_related("user")
    for profile in scouts:
        profiles.append((profile.user, profile, _scout_details(profile), "Scout"))

    organizations = Organization.objects.filter(
        user_id__in=user_ids,
        user__is_active=True,
        status="ACTIVE",
    ).select_related(
        "user",
        "category",
        "domain",
        "sports_profile__sport",
    )
    for profile in organizations:
        profiles.append((
            profile.user,
            profile,
            _organization_details(profile),
            "Organization",
        ))

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

    ecosystem_user_ids = get_ecosystem_user_ids(user)
    if not ecosystem_user_ids:
        return []

    focus_groups = {}
    for member, profile, details, member_type in _ecosystem_profiles(
        ecosystem_user_ids,
        user.pk,
    ):
        for detail in details:
            group = focus_groups.setdefault(detail, {})
            group[member.pk] = {
                "user": member,
                "profile": profile,
                "type": member_type,
            }

    _, viewer_details = get_ecosystem_details(user)
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
            + (12 if focus in viewer_details else 0),
        )
        recommendations.append({
            "name": focus.title(),
            "focus": focus,
            "member_count": len(members_by_id),
            "member_types": member_types,
            "score": score,
            "viewer_is_member": viewer_is_member,
            "reason": (
                f"{len(members_by_id)} active members share this focus"
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

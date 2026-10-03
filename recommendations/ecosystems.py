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

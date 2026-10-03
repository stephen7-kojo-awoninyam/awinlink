from django.shortcuts import render
from twisted import python
from django.contrib.auth import get_user_model
from django.urls import reverse
from talents.models import TalentProfile
from skills.models import Skill
from domains.models import TalentDomain
from opportunities.models import Opportunity
from django.shortcuts import render
from django.db.models import Q

from talents.models import TalentProfile
from skills.models import Skill
from domains.models import TalentDomain
from opportunities.models import Opportunity

from django.db.models import Q


def talent_search(request):
    user_model = get_user_model()

    talents = TalentProfile.objects.select_related(
        "user"
    ).prefetch_related(
        "skills",
        "domains"
    ).filter(
        profile_visibility__in=["PUBLIC", "ORGANIZATIONS"]
    )

    # ==========================================
    # GET FILTERS
    # ==========================================

    search = request.GET.get("search", "").strip()
    role = request.GET.get("role")
    skill = request.GET.get("skill")
    domain = request.GET.get("domain")
    country = request.GET.get("country")
    experience = request.GET.get("experience")
    availability = request.GET.get("availability")
    work_type = request.GET.get("work_type")
    verified = request.GET.get("verified")

    # ==========================================
    # GENERAL SEARCH
    # ==========================================

    username_search = search.startswith("@")
    username_query = search[1:].strip() if username_search else ""
    user_results = []

    if username_search:
        users = user_model.objects.filter(
            username__iexact=username_query,
            is_active=True,
        ).exclude(
            Q(role="ADMIN") | Q(is_superuser=True)
        ).select_related(
            "talent_profile",
            "coach_profile",
            "scout_profile",
            "organization_profile__category",
            "organization_profile__domain",
        )

        for user in users:
            profile = None
            profile_url = ""
            display_name = user.get_full_name() or user.username
            detail = ""
            location = ""
            photo = user.profile_picture

            if user.role == "ATHLETE":
                profile = getattr(user, "talent_profile", None)
                if profile is None:
                    continue

                is_owner = (
                    request.user.is_authenticated
                    and request.user.pk == user.pk
                )
                can_view_organization_profile = (
                    request.user.is_authenticated
                    and request.user.role == "ORGANIZATION"
                    and profile.profile_visibility == "ORGANIZATIONS"
                )
                if not is_owner and not can_view_organization_profile:
                    if profile.profile_visibility != "PUBLIC":
                        continue

                detail = profile.headline or profile.talent_area or ""
                location = ", ".join(
                    value for value in (profile.city, profile.country) if value
                )
                photo = profile.profile_photo or photo
                profile_url = reverse("talent_profile", args=[profile.pk])

            elif user.role == "COACH":
                profile = getattr(user, "coach_profile", None)
                if profile:
                    detail = (
                        profile.headline
                        or profile.specialization
                        or (
                            f"{profile.get_coach_category_display()} Coach"
                            if profile.coach_category
                            else ""
                        )
                    )
                    location = ", ".join(
                        value for value in (profile.city, profile.country) if value
                    )
                    photo = profile.profile_photo or photo
                if request.user.is_authenticated and request.user.pk == user.pk:
                    profile_url = reverse("coach_profile")

            elif user.role == "SCOUT":
                profile = getattr(user, "scout_profile", None)
                if profile:
                    detail = (
                        profile.headline
                        or profile.specialization
                        or (
                            f"{profile.get_scout_category_display()} Scout"
                            if profile.scout_category
                            else ""
                        )
                    )
                    location = ", ".join(
                        value for value in (profile.city, profile.country) if value
                    )
                if request.user.is_authenticated and request.user.pk == user.pk:
                    profile_url = reverse("scout_dashboard")

            elif user.role == "ORGANIZATION":
                profile = getattr(user, "organization_profile", None)
                if profile:
                    display_name = profile.name
                    detail = (
                        profile.category.name
                        if profile.category
                        else ""
                    )
                    location = ", ".join(
                        value for value in (profile.city, profile.country) if value
                    )
                    photo = profile.logo or photo
                    profile_url = reverse(
                        "organization_profile",
                        args=[profile.pk],
                    )

            user_results.append(
                {
                    "user": user,
                    "display_name": display_name,
                    "role_label": user.get_role_display(),
                    "detail": detail,
                    "location": location,
                    "photo": photo,
                    "profile_url": profile_url,
                }
            )

    elif search:
        talents = talents.filter(
            Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
            | Q(user__username__icontains=search)
            | Q(headline__icontains=search)
            | Q(talent_area__icontains=search)
            | Q(biography__icontains=search)
            | Q(country__icontains=search)
            | Q(city__icontains=search)
        )

    # ==========================================
    # ROLE
    # ==========================================

    if role:
        talents = talents.filter(
            user__role=role
        )

    # ==========================================
    # SKILL
    # ==========================================

    if skill:
        talents = talents.filter(
            skills__id=skill
        )

    # ==========================================
    # DOMAIN
    # ==========================================

    if domain:
        talents = talents.filter(
            domains__id=domain
        )

    # ==========================================
    # COUNTRY
    # ==========================================

    if country:
        talents = talents.filter(
            country__icontains=country
        )

    # ==========================================
    # EXPERIENCE
    # ==========================================

    if experience:
        talents = talents.filter(
            experience_level=experience
        )

    # ==========================================
    # AVAILABILITY
    # ==========================================

    if availability:
        talents = talents.filter(
            availability_status=availability
        )

    # ==========================================
    # WORK TYPE
    # ==========================================

    if work_type:
        talents = talents.filter(
            preferred_work_type=work_type
        )

    # ==========================================
    # VERIFIED
    # ==========================================

    if verified == "true":
        talents = talents.filter(
            verified=True
        )

    # ==========================================
    # PREVENT DUPLICATE RESULTS
    # ==========================================

    talents = talents.distinct()

    # ==========================================
    # FILTER DATA FOR TEMPLATE
    # ==========================================

    skills = Skill.objects.all().order_by(
        "name"
    )

    domains = TalentDomain.objects.all().order_by(
        "name"
    )

    # Get roles directly from User model
    role_choices = user_model._meta.get_field(
        "role"
    ).choices

    context = {
        "talents": talents,
        "user_results": user_results,
        "username_search": username_search,
        "username_query": username_query,
        "skills": skills,
        "domains": domains,
        "role_choices": role_choices,

        "experience_choices":
            TalentProfile.EXPERIENCE_LEVELS,

        "availability_choices":
            TalentProfile.AVAILABILITY_CHOICES,

        "work_type_choices":
            TalentProfile.WORK_TYPES,
    }

    return render(
        request,
        "search/search.html",
        context
    )



    
    


def opportunity_search(request):

    opportunities = Opportunity.objects.select_related(
        "organization",
        "domain"
    ).prefetch_related(
        "skills"
    ).filter(
        active=True
    )

    # ==========================================
    # GET FILTERS
    # ==========================================

    opportunity_type = request.GET.get("opportunity_type")
    domain = request.GET.get("domain")
    skill = request.GET.get("skill")
    experience = request.GET.get("experience")
    work_type = request.GET.get("work_type")
    location = request.GET.get("location")

    # ==========================================
    # OPPORTUNITY TYPE
    # ==========================================

    if opportunity_type:
        opportunities = opportunities.filter(
            opportunity_type=opportunity_type
        )

    # ==========================================
    # DOMAIN
    # ==========================================

    if domain:
        opportunities = opportunities.filter(
            domain_id=domain
        )

    # ==========================================
    # SKILL
    # ==========================================

    if skill:
        opportunities = opportunities.filter(
            skills__id=skill
        )

    # ==========================================
    # EXPERIENCE
    # ==========================================

    if experience:
        opportunities = opportunities.filter(
            experience_level=experience
        )

    # ==========================================
    # WORK TYPE
    # ==========================================

    if work_type:
        opportunities = opportunities.filter(
            work_type=work_type
        )

    # ==========================================
    # LOCATION
    # ==========================================

    if location:
        opportunities = opportunities.filter(
            location__icontains=location
        )

    opportunities = opportunities.distinct()

    # ==========================================
    # FILTER OPTIONS
    # ==========================================

    skills = Skill.objects.all().order_by(
        "name"
    )

    domains = TalentDomain.objects.all().order_by(
        "name"
    )

    context = {

        "opportunities": opportunities,

        "skills": skills,

        "domains": domains,

        "opportunity_type_choices":
            Opportunity.OPPORTUNITY_TYPES,

        "experience_choices":
            Opportunity.EXPERIENCE_LEVELS,

        "work_type_choices":
            Opportunity.WORK_TYPES,

    }

    return render(
        request,
        "search/opportunity_search.html",
        context
    )    
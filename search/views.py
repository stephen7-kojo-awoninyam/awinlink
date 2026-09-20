from django.shortcuts import render
from twisted import python
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

    search = request.GET.get("search")
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

    if search:
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
    User = TalentProfile._meta.get_field(
        "user"
    ).remote_field.model

    role_choices = User._meta.get_field(
        "role"
    ).choices

    context = {
        "talents": talents,
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
        "search/talent_search.html",
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
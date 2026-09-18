from django.shortcuts import render, redirect, get_object_or_404

from django.contrib.auth.decorators import login_required

from organizations.models import Organization

from talents.models import TalentProfile

from .forms import OpportunityForm

from .models import Opportunity

from applications.models import Application

from notifications.models import Notification

from recommendations.services import RecommendationEngine

from django.contrib import messages

from django.utils import timezone

from django.db.models import Q



# =====================================
# CREATE OPPORTUNITY
# =====================================

@login_required
def create_opportunity(request):


    organization = get_object_or_404(
        Organization,
        user=request.user
    )


    if request.method == "POST":


        form = OpportunityForm(
            request.POST
        )


        if form.is_valid():


            opportunity = form.save(
                commit=False
            )


            opportunity.organization = organization


            opportunity.save()


            form.save_m2m()


            return redirect(
                "organization_dashboard"
            )



    else:


        form = OpportunityForm()



    return render(

        request,

        "opportunities/create.html",

        {
            "form": form
        }

    )





# =====================================
# LIST / SEARCH OPPORTUNITIES
# =====================================

def opportunity_list(request):

    opportunities = Opportunity.objects.filter(
        active=True
    ).select_related(
        "organization",
        "domain"
    ).prefetch_related(
        "skills"
    )

    # =====================================
    # SEARCH
    # =====================================

    search = request.GET.get("search", "").strip()

    if search:

        opportunities = opportunities.filter(

            Q(title__icontains=search)
            |
            Q(description__icontains=search)
            |
            Q(organization__name__icontains=search)
            |
            Q(location__icontains=search)

        )


    # =====================================
    # DOMAIN
    # =====================================

    domain = request.GET.get("domain")

    if domain:

        opportunities = opportunities.filter(
            domain_id=domain
        )


    # =====================================
    # OPPORTUNITY TYPE
    # =====================================

    opportunity_type = request.GET.get(
        "opportunity_type"
    )

    if opportunity_type:

        opportunities = opportunities.filter(
            opportunity_type=opportunity_type
        )


    # =====================================
    # EXPERIENCE LEVEL
    # =====================================

    experience_level = request.GET.get(
        "experience_level"
    )

    if experience_level:

        opportunities = opportunities.filter(
            experience_level=experience_level
        )


    # =====================================
    # WORK TYPE
    # =====================================

    work_type = request.GET.get(
        "work_type"
    )

    if work_type:

        opportunities = opportunities.filter(
            work_type=work_type
        )


    # =====================================
    # LOCATION
    # =====================================

    location = request.GET.get(
        "location",
        ""
    ).strip()

    if location:

        opportunities = opportunities.filter(
            location__icontains=location
        )


    # =====================================
    # FILTER DATA
    # =====================================

    from domains.models import TalentDomain

    domains = TalentDomain.objects.all().order_by(
        "name"
    )


    # =====================================
    # RENDER
    # =====================================

    return render(

        request,

        "opportunities/list.html",

        {

            "opportunities": opportunities,

            "domains": domains,

            "opportunity_types":
                Opportunity.OPPORTUNITY_TYPES,

            "experience_levels":
                Opportunity.EXPERIENCE_LEVELS,

            "work_types":
                Opportunity.WORK_TYPES,

            "search": search,

            "selected_domain": domain,

            "selected_opportunity_type":
                opportunity_type,

            "selected_experience_level":
                experience_level,

            "selected_work_type":
                work_type,

            "location": location,

        }

    )

# =====================================
# OPPORTUNITY DETAIL
# =====================================

@login_required
def opportunity_detail(request, opportunity_id):

    opportunity = get_object_or_404(
        Opportunity,
        id=opportunity_id
    )

    application = None

    if request.user.is_authenticated:

        talent = TalentProfile.objects.filter(
            user=request.user
        ).first()

        if talent:

            application = Application.objects.filter(
                talent=talent,
                opportunity=opportunity
            ).first()

    return render(
        request,
        "opportunities/detail.html",
        {
            "opportunity": opportunity,
            "application": application,
            "today": timezone.localdate(),
        }
    )







# =====================================
# APPLY FOR OPPORTUNITY
# =====================================

@login_required
def apply_opportunity(request, opportunity_id):

    if request.method != "POST":
        return redirect(
            "opportunity_detail",
            opportunity_id=opportunity_id
        )

    talent = get_object_or_404(
        TalentProfile,
        user=request.user
    )

    opportunity = get_object_or_404(
        Opportunity,
        id=opportunity_id
    )

    # Check opportunity availability
    if not opportunity.active:
        messages.warning(
            request,
            "This opportunity is currently closed."
        )
        return redirect(
            "opportunity_detail",
            opportunity.id
        )

    # Check deadline
    if (
        opportunity.deadline
        and opportunity.deadline < timezone.localdate()
    ):
        messages.warning(
            request,
            "The application deadline for this opportunity has passed."
        )
        return redirect(
            "opportunity_detail",
            opportunity.id
        )

    # Safely create the application
    application, created = Application.objects.get_or_create(
        talent=talent,
        opportunity=opportunity,
        defaults={
            "message": request.POST.get("message", "").strip()
        }
    )

    # Application already existed
    if not created:
        messages.info(
            request,
            "You have already applied for this opportunity."
        )
        return redirect(
            "opportunity_detail",
            opportunity.id
        )

    # Notify organization only for a new application
    Notification.objects.create(
        user=opportunity.organization.user,
        sender=request.user,
        notification_type="APPLICATION",
        message=(
            f"{talent.user.get_full_name()} "
            f"applied for {opportunity.title}."
        )
    )

    messages.success(
        request,
        "Your application has been submitted successfully."
    )

    return redirect(
        "opportunity_detail",
        opportunity.id
    )





# =====================================
# ORGANIZATION AI TALENT RECOMMENDATION
# =====================================

@login_required
def opportunity_recommendations(request, opportunity_id):


    organization = get_object_or_404(

        Organization,

        user=request.user

    )


    opportunity = get_object_or_404(

        Opportunity,

        id=opportunity_id,

        organization=organization

    )



    recommendations = RecommendationEngine.recommend_talents(

        opportunity

    )



    return render(

        request,

        "organizations/recommendations.html",

        {

            "opportunity": opportunity,

            "recommendations": recommendations

        }

    )








# =====================================
# TALENT AI OPPORTUNITY RECOMMENDATION
# =====================================

@login_required
def recommended_opportunities(request):


    talent = get_object_or_404(

        TalentProfile,

        user=request.user

    )



    opportunities = Opportunity.objects.filter(

        active=True

    ).select_related(

        "organization",

        "domain"

    ).prefetch_related(

        "skills"

    )



    recommendations = []



    for opportunity in opportunities:



        score = RecommendationEngine.calculate_opportunity_score(

            talent,

            opportunity

        )



        recommendations.append(

            {

                "opportunity": opportunity,

                "score": score

            }

        )



    recommendations.sort(

        key=lambda x:x["score"],

        reverse=True

    )



    return render(

        request,

        "opportunities/recommendations.html",

        {

            "recommendations": recommendations

        }

    )








# =====================================
# TALENT APPLICATION HISTORY
# =====================================

@login_required
def my_applications(request):

    talent = TalentProfile.objects.filter(
        user=request.user
    ).first()

    if not talent:

        return render(
            request,
            "opportunities/my_applications.html",
            {
                "applications": [],
                "no_talent_profile": True
            }
        )


    applications = Application.objects.filter(

        talent=talent

    ).select_related(

        "opportunity",
        "opportunity__organization"

    ).order_by(

        "-created_at"

    )


    return render(

        request,

        "opportunities/my_applications.html",

        {
            "applications": applications,
            "no_talent_profile": False
        }

    )
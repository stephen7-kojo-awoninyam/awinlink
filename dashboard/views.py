from django.shortcuts import render,redirect,get_object_or_404

from accounts.models import User

from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

from django.contrib.auth import get_user_model

from coaches.models import CoachProfile
from talents.models import TalentProfile, VerificationRequest

from organizations.models import Organization

from opportunities.models import Opportunity

from applications.models import Application

from django.contrib.auth import get_user_model

from django.db.models import Count
from django.http import HttpResponseBadRequest
from organizations.permissions import require_user_organization_active, require_request_organization, OrganizationCapability

from skills.models import Skill
# Create your views here.


@login_required
def dashboard(request):

    user = request.user


    # =====================================================
    # SUPERUSER / ADMIN
    # =====================================================

    if user.is_superuser or user.role == "ADMIN":

        context = {

            "total_users": User.objects.count(),

            "total_talents": TalentProfile.objects.count(),

            "total_organizations": Organization.objects.count(),

            "total_opportunities": Opportunity.objects.count(),

            "total_applications": Application.objects.count(),

            "pending_verifications": VerificationRequest.objects.filter(
                status="PENDING"
            ).count(),

        }

        return render(
            request,
            "dashboard/admin_dashboard.html",
            context
        )


    # =====================================================
    # ATHLETE
    # =====================================================

    if user.role == "ATHLETE":

        profile = TalentProfile.objects.filter(
            user=user
        ).first()

        if profile:
            return redirect("talent_dashboard")

        return redirect("select_talent_category")


    # =====================================================
    # ORGANIZATION
    # =====================================================

    elif user.role == "ORGANIZATION":
        from organizations.views import organization_dashboard
        return organization_dashboard(request)


    # =====================================================
    # SCOUT
    # =====================================================

    elif user.role == "SCOUT":
        
        profile = TalentProfile.objects.filter(
        user=user
        ).first()


        return render(
            request,
            "dashboard/scout_dashboard.html",
            {
               "profile": profile,
            }
        )


    # =====================================================
    # COACH
    # =====================================================

    elif user.role == "COACH":

        profile = CoachProfile.objects.filter(
            user=user
        ).first()

        if not profile:
            return redirect("select_coach_category")

        if not profile.coach_category:
            return redirect("select_coach_category")

        return redirect("coach_profile")


    # =====================================================
    # UNKNOWN ROLE
    # =====================================================

    return render(
        request,
        "dashboard/dashboard.html"
    )
        
        
@login_required
def verification_requests(request):


    if not request.user.is_superuser and request.user.role != "ADMIN":

        return redirect("home")



    requests = VerificationRequest.objects.filter(

        status="PENDING"

    ).select_related(

        "talent"

    )


    return render(

        request,

        "dashboard/verification_requests.html",

        {
            "requests": requests
        }

    )
    
    
    
@login_required
@require_POST
def approve_verification(request, request_id):


    if not request.user.is_superuser and request.user.role != "ADMIN":

        return redirect("home")



    verification = get_object_or_404(

        VerificationRequest,

        id=request_id

    )


    verification.status = "APPROVED"

    verification.save()



    talent = verification.talent


    talent.verified = True

    talent.save()



    return redirect(

        "verification_requests"

    )  
    
    
@login_required
@require_POST
def reject_verification(request, request_id):


    if not request.user.is_superuser and request.user.role != "ADMIN":

        return redirect("home")



    verification = get_object_or_404(

        VerificationRequest,

        id=request_id

    )


    verification.status = "REJECTED"

    verification.save()



    return redirect(

        "verification_requests"

    ) 
    
    
    
@login_required
def user_management(request):


    if not request.user.is_superuser and request.user.role != "ADMIN":

        return redirect("home")



    User = get_user_model()



    users = User.objects.all().order_by(
        "-date_joined"
    )


    return render(

        request,

        "dashboard/user_management.html",

        {
            "users": users
        }

    )  
    
    
@login_required
@require_POST
def toggle_user_status(request, user_id):


    if not request.user.is_superuser and request.user.role != "ADMIN":

        return redirect("home")



    User = get_user_model()



    user = get_object_or_404(

        User,

        id=user_id

    )


    user.is_active = not user.is_active


    user.save()



    return redirect(

        "user_management"

    )   
    
    
@login_required
def talent_management(request):

    if not request.user.is_superuser and request.user.role != "ADMIN":

        return redirect("home")


    talents = TalentProfile.objects.select_related(
        "user"
    ).all().order_by(
        "-created_at"
    )


    return render(
        request,
        "dashboard/talent_management.html",
        {
            "talents": talents
        }
    )
    
@login_required
@require_POST
def toggle_talent_status(request, talent_id):


    if not request.user.is_superuser and request.user.role != "ADMIN":

        return redirect("home")


    talent = get_object_or_404(
        TalentProfile,
        id=talent_id
    )


    talent.user.is_active = not talent.user.is_active

    talent.user.save()


    return redirect(
        "talent_management"
    )
    
    
@login_required
def organization_management(request):


    if not request.user.is_superuser and request.user.role != "ADMIN":

        return redirect("home")



    organizations = Organization.objects.select_related(
        "user"
    ).all().order_by(
        "-created_at"
    )


    return render(

        request,

        "dashboard/organization_management.html",

        {
            "organizations": organizations
        }

    )
    
    
@login_required
@require_POST
def toggle_organization_status(request, organization_id):


    if not request.user.is_superuser and request.user.role != "ADMIN":

        return redirect("home")



    organization = get_object_or_404(

        Organization,

        id=organization_id

    )


    desired_status = request.POST.get("status")
    if desired_status not in {"ACTIVE", "INACTIVE"}:
        return HttpResponseBadRequest("Choose Suspend or Reactivate.")

    # A repeated submission is safe; merged/closed records are not reopened.
    updated = Organization.objects.filter(
        pk=organization.pk, status__in={"ACTIVE", "INACTIVE"},
    ).update(status=desired_status)
    if not updated:
        return HttpResponseBadRequest(
            "Only active or inactive organizations can be suspended or reactivated."
        )



    return redirect(

        "organization_management"

    )      
    
    
@login_required
def admin_reports(request):


    if not request.user.is_superuser and request.user.role != "ADMIN":

        return redirect("home")



    # User statistics

    User = get_user_model()


    users_by_role = User.objects.values(
        "role"
    ).annotate(
        total=Count("id")
    )



    # Talent countries

    talent_by_country = TalentProfile.objects.values(

        "country"

    ).annotate(

        total=Count("id")

    ).order_by(
        "-total"
    )[:10]



    # Popular skills

    popular_skills = Skill.objects.values(

        "name"

    ).annotate(

        total=Count("talentprofile")

    ).order_by(
        "-total"
    )[:10]



    # Opportunity statistics

    opportunity_stats = {


        "active": Opportunity.objects.filter(
            active=True
        ).count(),


        "closed": Opportunity.objects.filter(
            active=False
        ).count(),


    }



    # Application statistics

    application_stats = {


        "pending": Application.objects.filter(
            status="PENDING"
        ).count(),


        "accepted": Application.objects.filter(
            status="ACCEPTED"
        ).count(),


        "rejected": Application.objects.filter(
            status="REJECTED"
        ).count(),


    }



    context = {


        "users_by_role": users_by_role,


        "talent_by_country": talent_by_country,


        "popular_skills": popular_skills,


        "opportunity_stats": opportunity_stats,


        "application_stats": application_stats,


    }



    return render(

        request,

        "dashboard/admin_reports.html",

        context

    )                 
                 

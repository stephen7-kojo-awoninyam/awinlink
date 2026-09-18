from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from events.models import Event

from .models import (
    Organization,
    OrganizationCategory
)

from .forms import OrganizationForm


from analytics.models import (
    TalentProfileView,
    RecommendationHistory
)


from recommendations.services import RecommendationEngine


from shortlists.models import Shortlist


from applications.models import Application


from invitations.models import Invitation


from notifications.models import Notification


from opportunities.models import Opportunity


from talents.models import TalentProfile


from recruitment.models import RecruitmentStage

from connections.models import OrganizationFollow




# ==================================================
# ORGANIZATION DASHBOARD
# ==================================================
@login_required
def organization_dashboard(request):

    organization = get_object_or_404(
        Organization,
        user=request.user
    )

    events = Event.objects.filter(
        organizer=organization
    ).annotate(
        participants=Count("registrations"),
        approved=Count(
            "registrations",
            filter=Q(
                registrations__status="APPROVED"
            )
        ),
        attended=Count(
            "registrations",
            filter=Q(
                registrations__status="ATTENDED"
            )
        )
    )

    opportunities = Opportunity.objects.filter(
        organization=organization
    ).select_related(
        "domain"
    )


    active_opportunities = opportunities.filter(
        active=True
    )


    applications = Application.objects.filter(
        opportunity__organization=organization
    ).select_related(
        "talent",
        "talent__user",
        "opportunity"
    ).order_by(
        "-created_at"
    )



    invitations = Invitation.objects.filter(
        organization=organization
    ).select_related(
        "talent",
        "talent__user",
        "opportunity"
    ).order_by(
        "-created_at"
    )



    recommended_talents = []


    for opportunity in active_opportunities:


        matches = RecommendationEngine.recommend_talents(
            opportunity
        )


        for match in matches:


            RecommendationHistory.objects.get_or_create(

                organization=organization,

                talent=match["talent"],

                opportunity=opportunity,

                defaults={
                    "score":match["score"]
                }

            )


            recommended_talents.append({

                "talent":match["talent"],

                "opportunity":opportunity,

                "score":match["score"],

                "reasons":match.get(
                    "reasons",
                    []
                )

            })



    recommended_talents.sort(
        key=lambda x:x["score"],
        reverse=True
    )


    recommended_talents = recommended_talents[:10]



    total_talent_views = TalentProfileView.objects.filter(
        organization=organization
    ).count()



    total_invitations = invitations.count()


    accepted_invitations = invitations.filter(
        status="ACCEPTED"
    ).count()


    acceptance_rate = 0


    if total_invitations:

        acceptance_rate = round(
            (accepted_invitations / total_invitations) * 100,
            2
        )



    notifications = Notification.objects.filter(
        user=request.user
    ).order_by(
        "-created_at"
    )[:5]



    top_opportunities = opportunities.annotate(
        application_count=Count(
            "applications"
        )
    ).order_by(
        "-application_count"
    )[:5]



    favorite_talents = Shortlist.objects.filter(
        organization=organization,
        starred=True
    ).count()



    shortlisted_talents_count = Shortlist.objects.filter(
        organization=organization
    ).count()



    profile_fields = [

        organization.name,
        organization.category,
        organization.domain,
        organization.country,
        organization.city,
        organization.description,
        organization.logo,
        organization.website,
        organization.email,
        organization.phone,

    ]


    completed = sum(
        1 for field in profile_fields if field
    )


    organization_profile_completion = round(
        (completed / len(profile_fields))*100,
        2
    )



    context = {


        "organization":organization,


        "opportunities":opportunities,


        "applications":applications,


        "recent_applications":applications[:5],


        "total_opportunities":opportunities.count(),


        "active_opportunities":active_opportunities.count(),


        "closed_opportunities":opportunities.filter(
            active=False
        ).count(),


        "total_applications":applications.count(),


        "pending_applications":applications.filter(
            status="PENDING"
        ).count(),


        "accepted_applications":applications.filter(
            status="ACCEPTED"
        ).count(),


        "rejected_applications":applications.filter(
            status="REJECTED"
        ).count(),


        "invitations":invitations,


        "total_invitations":total_invitations,


        "recommended_talents":recommended_talents,


        "total_recommendations":len(
            recommended_talents
        ),


        "total_talent_views":total_talent_views,


        "acceptance_rate":acceptance_rate,


        "favorite_talents":favorite_talents,


        "shortlisted_talents_count":shortlisted_talents_count,


        "organization_profile_completion":
        organization_profile_completion,


        "notifications":notifications,


        "top_opportunities":top_opportunities,

    }


    return render(
        request,
        "organizations/dashboard.html",
        context
    )



# ==================================================
# ORGANIZATION APPLICATIONS
# ==================================================

@login_required
def organization_applications(request):

    organization = get_object_or_404(
        Organization,
        user=request.user
    )


    applications = Application.objects.filter(

        opportunity__organization=organization

    ).select_related(

        "talent",
        "talent__user",
        "opportunity"

    ).prefetch_related(

        "talent__skills",
        "talent__domains"

    ).order_by(

        "-created_at"

    )


    return render(

        request,

        "organizations/applications.html",

        {
            "organization": organization,
            "applications": applications
        }

    )




# ==================================================
# EDIT PROFILE
# ==================================================

@login_required
def edit_organization_profile(request):


    organization=get_object_or_404(
        Organization,
        user=request.user
    )


    if request.method=="POST":

        form=OrganizationForm(
            request.POST,
            request.FILES,
            instance=organization
        )


        if form.is_valid():

            form.save()

            return redirect(
                "organization_dashboard"
            )


    else:

        form=OrganizationForm(
            instance=organization
        )


    return render(
        request,
        "organizations/edit_profile.html",
        {
            "form":form,
            "organization":organization
        }
    )
    
# ==================================================
# ORGANIZATION PROFILE
# ==================================================

def organization_profile(request, organization_id):


    organization = get_object_or_404(

        Organization,

        id=organization_id

    )


    opportunities = Opportunity.objects.filter(

        organization=organization,

        active=True

    )


    followers = organization.followers.count()



    return render(

        request,

        "organizations/profile.html",

        {

            "organization":organization,

            "opportunities":opportunities,

            "followers":followers

        }

    )

# ==================================================
# ORGANIZATION DIRECTORY
# ==================================================

def organization_directory(request):


    organizations = Organization.objects.all().select_related(

        "category",

        "domain"

    )



    # ==========================
    # Search
    # ==========================

    query = request.GET.get(
        "q"
    )


    if query:


        organizations = organizations.filter(

            Q(name__icontains=query)

            |

            Q(country__icontains=query)

            |

            Q(city__icontains=query)

        )




    # ==========================
    # Country Filter
    # ==========================

    country = request.GET.get(
        "country"
    )


    if country:


        organizations = organizations.filter(

            country__icontains=country

        )





    # ==========================
    # Category Filter
    # ==========================

    category = request.GET.get(
        "category"
    )


    if category:


        organizations = organizations.filter(

            category_id=category

        )





    # ==========================
    # Verified Organizations
    # ==========================

    verified = request.GET.get(
        "verified"
    )


    if verified == "true":


        organizations = organizations.filter(

            verified=True

        )




    categories = OrganizationCategory.objects.all()



    return render(

        request,

        "organizations/directory.html",

        {

            "organizations": organizations,

            "categories": categories

        }

    )





# ==================================================
# AI TALENT RECOMMENDATIONS
# ==================================================

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



    shortlisted_ids = Shortlist.objects.filter(

        organization=organization

    ).values_list(

        "talent_id",

        flat=True

    )




    for item in recommendations:


        item["shortlisted"] = (

            item["talent"].id in shortlisted_ids

        )




    return render(

        request,

        "organizations/recommendations.html",

        {

            "opportunity": opportunity,

            "recommendations": recommendations

        }

    )





# ==================================================
# INVITE TALENT
# ==================================================

@login_required
def invite_talent(request, talent_id, opportunity_id):


    organization = get_object_or_404(

        Organization,

        user=request.user

    )



    talent = get_object_or_404(

        TalentProfile,

        id=talent_id

    )



    opportunity = get_object_or_404(

        Opportunity,

        id=opportunity_id,

        organization=organization

    )




    if request.method == "POST":


        message = request.POST.get(
            "message"
        )



        Invitation.objects.get_or_create(

            organization=organization,

            talent=talent,

            opportunity=opportunity,

            defaults={

                "message":message

            }

        )



        RecruitmentStage.objects.update_or_create(

            organization=organization,

            talent=talent,

            opportunity=opportunity,

            defaults={

                "stage":"INVITED"

            }

        )



        return redirect(

            "organization_dashboard"

        )




    return render(

        request,

        "organizations/invite_talent.html",

        {

            "talent": talent,

            "opportunity": opportunity

        }

    )





# ==================================================
# TALENT SEARCH
# ==================================================

@login_required
def talent_search(request):


    talents = TalentProfile.objects.filter(

        availability_status="AVAILABLE"

    ).filter(

        Q(profile_visibility="PUBLIC")

        |

        Q(profile_visibility="ORGANIZATIONS")

    ).select_related(

        "user"

    )




    query=request.GET.get(
        "q"
    )



    if query:


        talents=talents.filter(

            Q(headline__icontains=query)

            |

            Q(biography__icontains=query)

            |

            Q(country__icontains=query)

            |

            Q(city__icontains=query)

        )





    country=request.GET.get(
        "country"
    )


    if country:


        talents=talents.filter(

            country__icontains=country

        )





    experience=request.GET.get(
        "experience"
    )


    if experience:


        talents=talents.filter(

            experience_level=experience

        )





    verified=request.GET.get(
        "verified"
    )


    if verified=="true":


        talents=talents.filter(

            verified=True

        )




    return render(

        request,

        "organizations/talent_search.html",

        {

            "talents":talents

        }

    )





# ==================================================
# SHORTLISTED TALENTS
# ==================================================

@login_required
def shortlisted_talents(request):


    organization=get_object_or_404(

        Organization,

        user=request.user

    )



    shortlisted=Shortlist.objects.filter(

        organization=organization

    ).select_related(

        "talent",

        "talent__user"

    )




    return render(

        request,

        "organizations/shortlisted_talents.html",

        {

            "shortlisted":shortlisted

        }

    )    
    
# ==================================================
# ORGANIZATION DISCOVERY
# ==================================================

def organization_list(request):


    organizations = Organization.objects.filter(

        status="ACTIVE"

    ).select_related(

        "category",
        "domain"

    ).order_by(

        "name"

    )



    query = request.GET.get("q")



    if query:


        organizations = organizations.filter(

            Q(name__icontains=query)
            |
            Q(country__icontains=query)
            |
            Q(city__icontains=query)

        )



    category = request.GET.get("category")


    if category:


        organizations = organizations.filter(

            category__name=category

        )



    return render(

        request,

        "organizations/list.html",

        {

            "organizations": organizations

        }

    )  
    
    
@login_required
def follow_organization(request, organization_id):


    organization = get_object_or_404(

        Organization,

        id=organization_id

    )


    OrganizationFollow.objects.get_or_create(

        user=request.user,

        organization=organization

    )


    return redirect(

        "organization_profile",

        organization.id

    )
    
    
@login_required
def unfollow_organization(request, organization_id):


    organization = get_object_or_404(

        Organization,

        id=organization_id

    )


    OrganizationFollow.objects.filter(

        user=request.user,

        organization=organization

    ).delete()


    return redirect(

        "organization_profile",

        organization.id

    )         
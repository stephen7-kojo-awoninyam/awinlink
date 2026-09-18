from django.shortcuts import render, get_object_or_404,redirect
from django.contrib.auth.decorators import login_required
from organizations.models import Organization
from .models import Shortlist
from organizations.models import Organization
from talents.models import TalentProfile
from .models import Shortlist
from notifications.utils import create_notification
from scouts.models import ScoutProfile
from django.contrib import messages
# Create your views here.

def get_user_organization(user):

    if user.role == "ORGANIZATION":

        return get_object_or_404(
            Organization,
            user=user
        )

    elif user.role == "SCOUT":

        scout = get_object_or_404(
            ScoutProfile,
            user=user
        )

        if not scout.organization:

            return None

        return scout.organization

    return None


@login_required
def organization_shortlist(request):

    organization = get_user_organization(request.user)

    if not organization:

        return render(
            request,
            "analytics/access_denied.html"
        )

    shortlisted_talents = (
        Shortlist.objects
        .filter(
            organization=organization
        )
        .select_related(
            "talent",
            "talent__user"
        )
        .order_by(
            "-created_at"
        )
    )

    total_shortlisted = shortlisted_talents.count()

    starred_talents = shortlisted_talents.filter(
        starred=True
    ).count()

    return render(
        request,
        "shortlists/list.html",
        {
            "organization": organization,
            "shortlisted_talents": shortlisted_talents,
            "total_shortlisted": total_shortlisted,
            "starred_talents": starred_talents,
        }
    )


@login_required
def add_to_shortlist(request, talent_id):


    organization = get_user_organization(request.user)

    if not organization:

        return render(
            request,
            "analytics/access_denied.html"
        )


    talent = get_object_or_404(

        TalentProfile,

        id=talent_id

    )


    shortlist, created = Shortlist.objects.get_or_create(

        organization=organization,

        talent=talent

    )


    if created:

        create_notification(

            user=talent.user,

            message=(

                f"{organization.name} saved your profile "
                "to their shortlist."

            ),

            notification_type="PROFILE_SAVED"

         )
        
        messages.success(
            request,
            "Talent added to the organization's shortlist."
        )

    else:

        messages.info(
            request,
            "Talent is already shortlisted."
        )


    return redirect(
        request.META.get(
            "HTTP_REFERER",
            "organization_shortlist"
        )
    )



@login_required
def remove_from_shortlist(request, talent_id):

    organization = get_user_organization(request.user)

    if not organization:

        return render(
            request,
            "analytics/access_denied.html"
        )

    shortlist = get_object_or_404(
        Shortlist,
        organization=organization,
        talent_id=talent_id
    )

    shortlist.delete()

    return redirect(
        "organization_shortlist"
    )
    
@login_required
def toggle_star(request, talent_id):

    organization = get_user_organization(request.user)

    if not organization:

        return render(
            request,
            "analytics/access_denied.html"
        )

    shortlist = get_object_or_404(
        Shortlist,
        organization=organization,
        talent_id=talent_id
    )

    shortlist.starred = not shortlist.starred
    shortlist.save()

    return redirect(
        "organization_shortlist"
    )
    
    
@login_required
def update_notes(request, talent_id):

    organization = get_user_organization(request.user)

    if not organization:

        return render(
            request,
            "analytics/access_denied.html"
        )

    shortlist = get_object_or_404(
        Shortlist,
        organization=organization,
        talent_id=talent_id
    )

    if request.method == "POST":

        shortlist.notes = request.POST.get(
            "notes"
        )

        shortlist.save()

        return redirect(
            "organization_shortlist"
        )

    return render(
        request,
        "shortlists/update_notes.html",
        {
            "shortlist": shortlist
        }
    )    
    
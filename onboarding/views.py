from django.shortcuts import render
from django.shortcuts import render, redirect
from .forms import RoleSelectionForm
from talents.forms import TalentProfileForm
from talents.models import TalentProfile
from django.contrib.auth.decorators import login_required
from organizations.forms import OrganizationForm
from organizations.models import Organization



# Create your views here.


def welcome(request):

    return render(
        request,
        "onboarding/welcome.html"
    )
    
    
    
def choose_role(request):

    return render(
        request,
        "onboarding/choose_role.html"
    )    
    
    
    


def choose_role(request):

    if request.method == "POST":

        role = request.POST.get("role")

        request.user.role = role
        request.user.save()

        if role == "TALENT":
            return redirect("talent_onboarding")

        elif role == "ORGANIZATION":
            return redirect("organization_onboarding")

        elif role == "COACH":
            return redirect("coach_onboarding")

        elif role == "SCOUT":
            return redirect("scout_onboarding")

    return render(
        request,
        "onboarding/choose_role.html"
    )  
    
    


@login_required
def talent_onboarding(request):

    profile, created = TalentProfile.objects.get_or_create(
        user=request.user
    )

    if request.method == "POST":

        form = TalentProfileForm(
            request.POST,
            request.FILES,
            instance=profile
        )

        if form.is_valid():

            form.save()

            return redirect(
                "talent_dashboard"
            )

    else:

        form = TalentProfileForm(
            instance=profile
        )

    return render(
        request,
        "onboarding/talent.html",
        {
            "form": form
        }
    )    
    

@login_required
def organization_onboarding(request):

    profile, created = Organization.objects.get_or_create(
        user=request.user
    )


    if request.method == "POST":

        form = OrganizationForm(
            request.POST,
            request.FILES,
            instance=profile
        )


        if form.is_valid():

            form.save()

            return redirect(
                "organization_dashboard"
            )


    else:

        form = OrganizationForm(
            instance=profile
        )


    return render(
        request,
        "onboarding/organization.html",
        {
            "form": form
        }
    )       
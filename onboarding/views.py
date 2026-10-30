from django.shortcuts import render, redirect
from .forms import RoleSelectionForm
from talents.forms import TalentProfileForm
from talents.models import TalentProfile
from django.contrib.auth.decorators import login_required
from organizations.forms import OrganizationForm
from organizations.models import Organization
from accounts.models import User
from accounts.roles import PUBLIC_ROLES
from django.db import transaction
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_http_methods



# Create your views here.


def welcome(request):

    return render(
        request,
        "onboarding/welcome.html"
    )
    
    
    
@login_required
@require_http_methods(["GET", "POST"])
def choose_role(request):
    form = RoleSelectionForm(request.POST if request.method == 'POST' else None)
    # Re-read under a lock: a concurrent trusted admin promotion must not be
    # overwritten by a stale browser user's role or unrelated account fields.
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=request.user.pk)
        if not user.is_active:
            raise PermissionDenied('This account is unavailable.')
        if user.role == 'ADMIN' or user.is_staff or user.is_superuser:
            return redirect('dashboard')
        # Older onboarding stored TALENT instead of ATHLETE. Allow that account
        # to select a public role without bulk rewriting historical accounts.
        if user.role not in PUBLIC_ROLES and user.role != 'TALENT':
            raise PermissionDenied('This account requires administrator review.')
        if request.method == 'POST' and form.is_valid():
            user.role = form.cleaned_data['role']
            user.save(update_fields=['role'])
            return redirect({
                'ATHLETE': 'talent_onboarding',
                'ORGANIZATION': 'organization_onboarding',
                'COACH': 'select_coach_category',
                'SCOUT': 'select_scout_category',
            }[user.role])
    return render(request, 'onboarding/choose_role.html', {'form': form},
                  status=400 if request.method == 'POST' else 200)
    
    


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

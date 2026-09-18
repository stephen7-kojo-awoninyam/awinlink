from django.shortcuts import render

# Create your views here.
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required

from talents.models import TalentProfile

from .models import ScienceTechnologyTalentProfile
from .forms import ScienceTechnologyTalentProfileForm


@login_required
def science_technology_profile_setup(request):

    # ==========================================
    # GET THE CURRENT TALENT
    # ==========================================

    talent = get_object_or_404(
        TalentProfile,
        user=request.user
    )


    # ==========================================
    # ONLY SCIENCE & TECHNOLOGY TALENTS
    # ==========================================

    if talent.talent_category != "SCIENCE_TECHNOLOGY":

        return redirect("select_talent_category")


    # ==========================================
    # GET OR CREATE SCIENCE & TECHNOLOGY PROFILE
    # ==========================================

    science_profile, created = (
        ScienceTechnologyTalentProfile.objects.get_or_create(
            talent=talent
        )
    )


    # ==========================================
    # FORM SUBMISSION
    # ==========================================

    if request.method == "POST":

        form = ScienceTechnologyTalentProfileForm(
            request.POST,
            instance=science_profile
        )

        if form.is_valid():

            profile = form.save(
                commit=False
            )

            profile.talent = talent

            profile.save()

            return redirect(
                "talent_dashboard"
            )


    else:

        form = ScienceTechnologyTalentProfileForm(
            instance=science_profile
        )


    # ==========================================
    # RENDER
    # ==========================================

    return render(
        request,
        "science_technology/profile_setup.html",
        {
            "talent": talent,
            "science_profile": science_profile,
            "form": form,
        }
    )
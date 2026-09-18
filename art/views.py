from django.shortcuts import render

# Create your views here.

from django.shortcuts import (
    render,
    redirect,
    get_object_or_404,
)

from django.contrib.auth.decorators import login_required

from talents.models import TalentProfile

from .models import ArtsTalentProfile
from .forms import ArtsTalentProfileForm


# ============================================================
# ARTS PROFILE SETUP
# ============================================================

@login_required
def arts_profile_setup(request):

    # ========================================================
    # GET CURRENT TALENT
    # ========================================================

    talent = get_object_or_404(
        TalentProfile,
        user=request.user
    )


    # ========================================================
    # ONLY ARTS TALENTS
    # ========================================================

    if talent.talent_category != "ARTS":

        return redirect(
            "select_talent_category"
        )


    # ========================================================
    # GET OR CREATE ARTS PROFILE
    # ========================================================

    arts_profile, created = (
        ArtsTalentProfile.objects.get_or_create(
            talent=talent
        )
    )


    # ========================================================
    # FORM SUBMISSION
    # ========================================================

    if request.method == "POST":

        form = ArtsTalentProfileForm(
            request.POST,
            instance=arts_profile
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

        form = ArtsTalentProfileForm(
            instance=arts_profile
        )


    # ========================================================
    # RENDER
    # ========================================================

    return render(
        request,
        "arts/profile_setup.html",
        {
            "talent": talent,
            "arts_profile": arts_profile,
            "form": form,
        }
    )



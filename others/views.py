from django.shortcuts import render

# Create your views here.

from django.shortcuts import (
    render,
    redirect,
    get_object_or_404,
)

from django.contrib.auth.decorators import login_required

from talents.models import TalentProfile

from .models import OtherTalentProfile
from .forms import OtherTalentProfileForm


# ============================================================
# OTHER TALENT PROFILE SETUP
# ============================================================

@login_required
def other_profile_setup(request):

    # ========================================================
    # GET CURRENT TALENT
    # ========================================================

    talent = get_object_or_404(
        TalentProfile,
        user=request.user
    )

    # ========================================================
    # ONLY OTHER TALENTS
    # ========================================================

    if talent.talent_category != "OTHERS":

        return redirect(
            "select_talent_category"
        )

    # ========================================================
    # GET OR CREATE OTHER PROFILE
    # ========================================================

    other_profile, created = (
        OtherTalentProfile.objects.get_or_create(
            talent=talent
        )
    )

    # ========================================================
    # FORM SUBMISSION
    # ========================================================

    if request.method == "POST":

        form = OtherTalentProfileForm(
            request.POST,
            instance=other_profile
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

        form = OtherTalentProfileForm(
            instance=other_profile
        )

    # ========================================================
    # RENDER
    # ========================================================

    return render(
        request,
        "others/profile_setup.html",
        {
            "talent": talent,
            "other_profile": other_profile,
            "form": form,
        }
    )


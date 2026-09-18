from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404

from talents.models import TalentProfile
from .models import SportsTalentProfile
from .forms import SportsTalentProfileForm
# Create your views here.




@login_required
def sports_profile_setup(request):

    # ==========================================
    # GET THE CURRENT TALENT
    # ==========================================

    talent = get_object_or_404(
        TalentProfile,
        user=request.user
    )


    # ==========================================
    # ONLY SPORTS TALENTS
    # ==========================================

    if talent.talent_category != "SPORTS":

        return redirect("select_talent_category")


    # ==========================================
    # GET OR CREATE SPORTS PROFILE
    # ==========================================

    sports_profile, created = (
        SportsTalentProfile.objects.get_or_create(
            talent=talent
        )
    )


    # ==========================================
    # FORM SUBMISSION
    # ==========================================

    if request.method == "POST":

        form = SportsTalentProfileForm(
            request.POST,
            instance=sports_profile
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

        form = SportsTalentProfileForm(
            instance=sports_profile
        )


    # ==========================================
    # RENDER
    # ==========================================

    return render(
        request,
        "sports/profile_setup.html",
        {
            "talent": talent,
            "sports_profile": sports_profile,
            "form": form,
        }
    )
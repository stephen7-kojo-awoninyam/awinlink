from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404

from talents.models import TalentProfile
from .forms import SportsTalentProfileForm
from .models import (
    SportsTalentProfile,
    Sport,
    SportCategory,
)
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

            # --------------------------------------
            # Get values typed by the user
            # --------------------------------------

            sport_name = form.cleaned_data["sport"].strip()

            category_name = (
                form.cleaned_data["sport_category"].strip()
            )


            # --------------------------------------
            # FIND OR CREATE SPORT
            # --------------------------------------

            sport = Sport.objects.filter(
                name__iexact=sport_name
            ).first()

            if sport is None:

                sport = Sport.objects.create(
                    name=sport_name
                )


            # --------------------------------------
            # FIND OR CREATE CATEGORY
            # FOR THIS SPORT
            # --------------------------------------

            category = SportCategory.objects.filter(
                sport=sport,
                name__iexact=category_name
            ).first()

            if category is None:

                category = SportCategory.objects.create(
                    sport=sport,
                    name=category_name
                )


            # --------------------------------------
            # SAVE SPORTS PROFILE
            # --------------------------------------

            profile = form.save(
                commit=False
            )

            profile.talent = talent
            profile.sport = sport
            profile.sport_category = category

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
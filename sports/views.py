from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from talents.models import TalentProfile
from .forms import SportsTalentProfileForm
from talents.forms import SportsScoutProfileForm
from .models import (
    SportsTalentProfile,
    Sport,
    SportCategory,
)
# Create your views here.


@login_required
def sports_profile_setup(request):

    talent = get_object_or_404(
        TalentProfile,
        user=request.user
    )

    if talent.talent_category != "SPORTS":
        return redirect("select_talent_category")

    sports_profile, created = (
        SportsTalentProfile.objects.get_or_create(
            talent=talent
        )
    )

    is_scout = request.user.role == "SCOUT"

    # =========================================
    # SCOUT PROFILE
    # =========================================

    if is_scout:

        if request.method == "POST":

            form = SportsScoutProfileForm(
                request.POST
            )

            if form.is_valid():

                sport_name = form.cleaned_data["sport"].strip()
                category_name = form.cleaned_data[
                    "sport_category"
                ].strip()

                # -----------------------------
                # Get or create Sport
                # -----------------------------

                sport = Sport.objects.filter(
                    name__iexact=sport_name
                ).first()

                if sport is None:
                    sport = Sport.objects.create(
                        name=sport_name
                    )

                # -----------------------------
                # Get or create Sport Category
                # -----------------------------

                category = None

                if category_name:

                    category = SportCategory.objects.filter(
                        sport=sport,
                        name__iexact=category_name
                    ).first()

                    if category is None:
                        category = SportCategory.objects.create(
                            sport=sport,
                            name=category_name
                        )

                # -----------------------------
                # Save Scout sports profile
                # -----------------------------

                sports_profile.sport = sport
                sports_profile.sport_category = category
                sports_profile.bio = form.cleaned_data["bio"]

                sports_profile.save()

                return redirect(
                    "talent_dashboard"
                )

        else:

            form = SportsScoutProfileForm(
                initial={
                    "sport": (
                        sports_profile.sport.name
                        if sports_profile.sport
                        else ""
                    ),
                    "sport_category": (
                        sports_profile.sport_category.name
                        if sports_profile.sport_category
                        else ""
                    ),
                    "bio": sports_profile.bio,
                }
            )

    # =========================================
    # NORMAL SPORTS TALENT
    # =========================================

    else:

        if request.method == "POST":

            form = SportsTalentProfileForm(
                request.POST,
                instance=sports_profile
            )

            if form.is_valid():

                sport_name = form.cleaned_data[
                    "sport"
                ].strip()

                category_name = form.cleaned_data[
                    "sport_category"
                ].strip()

                sport = Sport.objects.filter(
                    name__iexact=sport_name
                ).first()

                if sport is None:
                    sport = Sport.objects.create(
                        name=sport_name
                    )

                category = SportCategory.objects.filter(
                    sport=sport,
                    name__iexact=category_name
                ).first()

                if category is None:
                    category = SportCategory.objects.create(
                        sport=sport,
                        name=category_name
                    )

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

    return render(
        request,
        "sports/profile_setup.html",
        {
            "talent": talent,
            "sports_profile": sports_profile,
            "form": form,
            "is_scout": is_scout,
        }
    )
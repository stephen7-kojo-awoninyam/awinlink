
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from .forms import AthleteProfileForm
from django.shortcuts import render, get_object_or_404
from .models import AthleteProfile
from .forms import AthleteMediaForm

# Create your views here.

@login_required
def create_profile(request):

    if request.method == "POST":

        form = AthleteProfileForm(
            request.POST,
            request.FILES
        )

        if form.is_valid():

            profile = form.save(commit=False)

            profile.user = request.user

            profile.save()

            return redirect(
                "athlete_profile",
                profile.id
            )

    else:

        form = AthleteProfileForm()


    return render(
        request,
        "athletes/create_profile.html",
        {
            "form": form
        }
    )




def athlete_profile(request, id):

    profile = get_object_or_404(
        AthleteProfile,
        id=id
    )

    return render(
        request,
        "athletes/profile.html",
        {
            "profile": profile
        }
    )




@login_required
def add_media(request):

    profile = AthleteProfile.objects.get(
        user=request.user
    )


    if request.method == "POST":

        form = AthleteMediaForm(
            request.POST,
            request.FILES
        )

        if form.is_valid():

            media = form.save(commit=False)

            media.athlete = profile

            media.save()

            return redirect(
                "athlete_profile",
                id=profile.id
            )

    else:

        form = AthleteMediaForm()


    return render(
        request,
        "athletes/add_media.html",
        {
            "form": form
        }
    )    
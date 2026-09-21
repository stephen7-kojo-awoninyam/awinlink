from talents.models import TalentProfile
from django.contrib.auth import login
from django.shortcuts import redirect, render
from .forms import UserRegistrationForm
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import login, logout
from organizations.models import Organization

# Create your views here.


def register(request):

    if request.method == "POST":

        form = UserRegistrationForm(request.POST)
        print("FORM DATA:")
        print(request.POST)


        if form.is_valid():
            
            print("FORM IS VALID")


            user = form.save()
            print("USER CREATED:", user.username)
            print("ROLE:", user.role)

            # Automatically create an organization profile
            if user.role == "ORGANIZATION":

                Organization.objects.create(

                    user=user,

                    name=form.cleaned_data["organization_name"],

                    email=form.cleaned_data["organization_email"],

                    website=form.cleaned_data["website"],

                    phone=user.phone_number,

                    country=user.country,

                )

            TalentProfile.objects.create(
                user=user
            )

            
            login(request, user)

            # Redirect users according to their account role
            if user.role == "ATHLETE":
                return redirect("select_talent_category")

            elif user.role == "SCOUT":
                return redirect("select_scout_category")

            elif user.role == "COACH":
                return redirect("select_coach_category")

            elif user.role == "ORGANIZATION":
                return redirect("dashboard")

            elif user.role == "ADMIN":
                return redirect("dashboard")

            return redirect("dashboard")


        
        else:

            print("FORM ERRORS:")
            print(form.errors)
        

    else:

        form = UserRegistrationForm()

    return render(

        request,

        "accounts/register.html",

        {

            "form": form

        }

    )




def user_login(request):

    if request.method == "POST":

        form = AuthenticationForm(request, data=request.POST)

        if form.is_valid():

            user = form.get_user()

            login(request, user)

            return redirect("dashboard")

    else:

        form = AuthenticationForm()

    return render(request, "accounts/login.html", {"form": form})


def user_logout(request):

    logout(request)

    return redirect("home")

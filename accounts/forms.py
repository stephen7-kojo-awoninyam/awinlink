from django import forms
from django.contrib.auth.forms import UserCreationForm

from django.contrib.auth.forms import AuthenticationForm

from .models import User


class UserRegistrationForm(UserCreationForm):

    email = forms.EmailField(required=True)
    
    # Organization-only fields
    organization_name = forms.CharField(
        required=False,
        label="Organization Name"
    )

    organization_email = forms.EmailField(
        required=False,
        label="Organization Email"
    )

    website = forms.URLField(
        required=False,
        label="Website"
    )

    class Meta:
        model = User
        fields = (
            "first_name",
            "last_name",
            "username",
            "email",
            "phone_number",
            "country",
            "role",
            "password1",
            "password2",
        )


class LoginForm(AuthenticationForm):
    pass        
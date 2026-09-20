from django import forms

from .models import AthleteProfile
from .models import AthleteMedia


class AthleteProfileForm(forms.ModelForm):

    sport = forms.CharField(
        required=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter your sport, e.g. Football, Basketball, Tennis",
            }
        )
    )

    category = forms.CharField(
        required=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter your category or discipline, e.g. Goalkeeper, Sprinter",
            }
        )
    )

    class Meta:
        model = AthleteProfile

        fields = [
            "sport",
            "category",
            "date_of_birth",
            "nationality",
            "height",
            "weight",
            "experience_level",
            "biography",
            "current_team",
            "profile_photo",
            "cover_photo",
        ]

        widgets = {
            "date_of_birth": forms.DateInput(
                attrs={
                    "type": "date"
                }
            ),

            "biography": forms.Textarea(
                attrs={
                    "rows": 5
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:

            if self.instance.sport:
                self.initial["sport"] = self.instance.sport.name

            if self.instance.category:
                self.initial["category"] = self.instance.category.name


class AthleteMediaForm(forms.ModelForm):

    class Meta:
        model = AthleteMedia

        fields = [
            "title",
            "media_type",
            "file",
            "description",
        ]
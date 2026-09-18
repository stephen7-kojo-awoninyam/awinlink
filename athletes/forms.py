from django import forms
from .models import AthleteProfile
from .models import AthleteMedia



class AthleteProfileForm(forms.ModelForm):

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
        
        


class AthleteMediaForm(forms.ModelForm):

    class Meta:

        model = AthleteMedia

        fields = [
            "title",
            "media_type",
            "file",
            "description",
        ]        
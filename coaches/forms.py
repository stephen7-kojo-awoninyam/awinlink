from django import forms

from .models import CoachProfile


class CoachCategoryForm(forms.ModelForm):

    class Meta:
        model = CoachProfile
        fields = ["coach_category"]

        widgets = {
            "coach_category": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
        }
        
class CoachProfileForm(forms.ModelForm):

    class Meta:
        model = CoachProfile
        fields = [
            "headline",
            "biography",
            "specialization",
            "experience_level",
            "years_of_experience",
            "sport",
            "country",
            "city",
            "organization",
            "certifications",
            "profile_photo",
            "cover_photo",
        ]

        widgets = {
            "headline": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Example: AI & Technology Mentor",
                }
            ),

            "biography": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                }
            ),

            "specialization": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Your coaching specialization",
                }
            ),

            "experience_level": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "years_of_experience": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": 0,
                }
            ),

            "sport": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "country": forms.TextInput(
                attrs={
                    "class": "form-control",
                }
            ),

            "city": forms.TextInput(
                attrs={
                    "class": "form-control",
                }
            ),

            "organization": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "certifications": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Coaching certifications and qualifications",
                }
            ),

            "profile_photo": forms.ClearableFileInput(
                attrs={
                    "class": "form-control",
                }
            ),

            "cover_photo": forms.ClearableFileInput(
                attrs={
                    "class": "form-control",
                }
            ),
        }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Show the Sport field only for Sports Coaches
        if (
            self.instance
            and self.instance.coach_category != "SPORTS"
        ):
            self.fields.pop("sport", None)         
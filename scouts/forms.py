from django import forms

from .models import ScoutProfile


class ScoutCategoryForm(forms.ModelForm):

    class Meta:
        model = ScoutProfile
        fields = ["scout_category"]

        widgets = {
            "scout_category": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
        }
        
class ScoutProfileForm(forms.ModelForm):

    class Meta:
        model = ScoutProfile
        fields = [
            "headline",
            "biography",
            "specialization",
            "country",
            "city",
            "organization",
        ]

        widgets = {
            "headline": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Example: Technology Talent Scout",
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
                    "placeholder": "What type of talent do you scout?",
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
        } 
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if (
            self.instance
            and self.instance.scout_category == "SPORTS"
        ):
            self.fields["specialization"].widget.attrs[
                "placeholder"
            ] = "Example: Football, Basketball, Athletics"

        elif (
            self.instance
            and self.instance.scout_category == "SCIENCE_TECHNOLOGY"
        ):
            self.fields["specialization"].widget.attrs[
                "placeholder"
            ] = "Example: Artificial Intelligence, Engineering, Robotics"

        elif (
            self.instance
            and self.instance.scout_category == "ARTS"
        ):
            self.fields["specialization"].widget.attrs[
                "placeholder"
            ] = "Example: Music, Graphic Design, Film, Fashion"

        elif (
            self.instance
            and self.instance.scout_category == "OTHERS"
        ):
            self.fields["specialization"].widget.attrs[
                "placeholder"
            ] = "Example: Business, Healthcare, Education, Other Talent"           
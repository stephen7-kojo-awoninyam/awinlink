from django import forms

from .models import (
    SportsTalentProfile,
    SportCategory,
)


class SportsTalentProfileForm(forms.ModelForm):

    class Meta:

        model = SportsTalentProfile

        fields = [
            "sport",
            "sport_category",
            "position",
            "height",
            "weight",
            "bio",
        ]

        widgets = {

            "sport": forms.Select(
                attrs={
                    "class": "form-select"
                }
            ),

            "sport_category": forms.Select(
                attrs={
                    "class": "form-select"
                }
            ),

            "position": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Example: Forward, Goalkeeper, Sprinter"
                }
            ),

            "height": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Height",
                    "step": "0.01"
                }
            ),

            "weight": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Weight",
                    "step": "0.01"
                }
            ),

            "bio": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "placeholder": (
                        "Tell us about yourself as a sporting talent..."
                    )
                }
            ),
        }

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.fields["sport_category"].queryset = (
            SportCategory.objects.none()
        )

        if self.instance and self.instance.pk:

            if self.instance.sport:

                self.fields["sport_category"].queryset = (
                    SportCategory.objects.filter(
                        sport=self.instance.sport
                    )
                )

        elif "sport" in self.data:

            try:

                sport_id = int(
                    self.data.get("sport")
                )

                self.fields["sport_category"].queryset = (
                    SportCategory.objects.filter(
                        sport_id=sport_id
                    )
                )

            except (TypeError, ValueError):

                pass
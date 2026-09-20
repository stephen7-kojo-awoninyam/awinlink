from django import forms

from .models import SportsTalentProfile


class SportsTalentProfileForm(forms.ModelForm):

    sport = forms.CharField(
        required=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter your sport, e.g. Football, Basketball, Tennis",
            }
        )
    )

    sport_category = forms.CharField(
        required=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter your sport category or discipline",
            }
        )
    )

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
            "position": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Example: Forward, Goalkeeper, Sprinter",
                }
            ),
            "height": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Height",
                    "step": "0.01",
                }
            ),
            "weight": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Weight",
                    "step": "0.01",
                }
            ),
            "bio": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "placeholder": (
                        "Tell us about yourself as a sporting talent..."
                    ),
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Show existing values when editing
        if self.instance and self.instance.pk:

            if self.instance.sport:
                self.initial["sport"] = self.instance.sport.name

            if self.instance.sport_category:
                self.initial["sport_category"] = (
                    self.instance.sport_category.name
                )
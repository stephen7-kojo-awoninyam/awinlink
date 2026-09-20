from django import forms

from talents.forms import SportsTalentProfileForm

class SportsScoutProfileForm(forms.Form):

    sport = forms.CharField(
        required=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "e.g. Football, Basketball, Athletics",
                "list": "sport-suggestions",
            }
        ),
        label="Sport",
        help_text="Enter the sport you specialize in scouting.",
    )

    sport_category = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "e.g. Youth Development, Academy Talent, Goalkeeping",
                "list": "sport-category-suggestions",
            }
        ),
        label="Sport Category / Scouting Area",
        help_text=(
            "Describe the category, level, position group, "
            "or area you specialize in scouting."
        ),
    )

    bio = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 6,
                "placeholder": (
                    "Describe your scouting background, experience, "
                    "approach to identifying talent, and areas of expertise."
                ),
            }
        ),
        label="Scouting Background",
        help_text=(
            "Describe your scouting background, experience, "
            "approach to identifying talent, and the areas of "
            "sporting talent you specialize in evaluating."
        ),
    )

from django import forms

from .models import ArtsTalentProfile


class ArtsTalentProfileForm(forms.ModelForm):

    class Meta:

        model = ArtsTalentProfile

        fields = [
            "specialization",
            "description",
            "discipline",
            "experience_description",
            "years_of_experience",
            "skills_description",
            "portfolio_description",
            "achievements_description",
            "creative_interests",
            "website",
            "portfolio_url",
            "instagram",
            "youtube",
        ]

        widgets = {

            # =====================================================
            # SPECIALIZATION
            # =====================================================

            "specialization": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "Example: Graphic Designer, Musician, "
                        "Actor, Photographer, Writer..."
                    )
                }
            ),

            # =====================================================
            # ABOUT TALENT
            # =====================================================

            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "placeholder": (
                        "Tell us about yourself, your creative work, "
                        "your abilities and what makes you unique..."
                    )
                }
            ),

            # =====================================================
            # DISCIPLINE
            # =====================================================

            "discipline": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "Example: Music, Visual Arts, Film, "
                        "Dance, Theatre, Writing, Design..."
                    )
                }
            ),

            # =====================================================
            # EXPERIENCE
            # =====================================================

            "experience_description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": (
                        "Describe your experience in your creative "
                        "or artistic field..."
                    )
                }
            ),

            "years_of_experience": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": 0,
                    "placeholder": "Years of experience"
                }
            ),

            # =====================================================
            # SKILLS
            # =====================================================

            "skills_description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": (
                        "Describe your creative, artistic, technical "
                        "or professional skills..."
                    )
                }
            ),

            # =====================================================
            # PORTFOLIO
            # =====================================================

            "portfolio_description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": (
                        "Tell us about your creative work, "
                        "projects, performances, designs, "
                        "productions or other work..."
                    )
                }
            ),

            # =====================================================
            # ACHIEVEMENTS
            # =====================================================

            "achievements_description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": (
                        "Describe awards, exhibitions, performances, "
                        "recognition or other achievements..."
                    )
                }
            ),

            # =====================================================
            # CREATIVE INTERESTS
            # =====================================================

            "creative_interests": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": (
                        "What areas of creativity, art, design "
                        "or entertainment interest you?"
                    )
                }
            ),

            # =====================================================
            # ONLINE PRESENCE
            # =====================================================

            "website": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "https://example.com"
                }
            ),

            "portfolio_url": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "https://portfolio.example.com"
                }
            ),

            "instagram": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "https://instagram.com/username"
                }
            ),

            "youtube": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "https://youtube.com/@username"
                }
            ),
        }


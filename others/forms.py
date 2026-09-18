
from django import forms

from .models import OtherTalentProfile


class OtherTalentProfileForm(forms.ModelForm):

    class Meta:

        model = OtherTalentProfile

        fields = [
            "specialization",
            "description",
            "field",
            "experience_description",
            "years_of_experience",
            "skills_description",
            "projects_description",
            "achievements_description",
            "interests",
            "website",
            "linkedin",
            "other_link",
        ]

        widgets = {

            # =====================================================
            # SPECIALIZATION
            # =====================================================

            "specialization": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "Example: Entrepreneur, Consultant, "
                        "Entrepreneurship Coach, Skilled Professional..."
                    )
                }
            ),

            # =====================================================
            # DESCRIPTION
            # =====================================================

            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "placeholder": (
                        "Tell us about yourself, your abilities, "
                        "experience, goals and what makes you unique..."
                    )
                }
            ),

            # =====================================================
            # FIELD
            # =====================================================

            "field": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "Example: Business, Agriculture, "
                        "Finance, Leadership, Hospitality..."
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
                        "Describe your professional or practical "
                        "experience..."
                    )
                }
            ),

            # =====================================================
            # YEARS OF EXPERIENCE
            # =====================================================

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
                        "Describe your professional, technical, "
                        "practical or specialized skills..."
                    )
                }
            ),

            # =====================================================
            # PROJECTS / WORK
            # =====================================================

            "projects_description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": (
                        "Tell us about projects, businesses, "
                        "initiatives or other work you have done..."
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
                        "Tell us about awards, achievements, "
                        "recognition or milestones..."
                    )
                }
            ),

            # =====================================================
            # INTERESTS
            # =====================================================

            "interests": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": (
                        "What areas, activities or subjects "
                        "are you interested in?"
                    )
                }
            ),

            # =====================================================
            # WEBSITE
            # =====================================================

            "website": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "https://example.com"
                }
            ),

            # =====================================================
            # LINKEDIN
            # =====================================================

            "linkedin": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "https://linkedin.com/in/username"
                    )
                }
            ),

            # =====================================================
            # OTHER LINK
            # =====================================================

            "other_link": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "https://example.com/your-work"
                    )
                }
            ),
        }


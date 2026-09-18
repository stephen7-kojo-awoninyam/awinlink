
from django import forms

from .models import ScienceTechnologyTalentProfile


class ScienceTechnologyTalentProfileForm(forms.ModelForm):

    class Meta:

        model = ScienceTechnologyTalentProfile

        fields = [
            "specialization",
            "description",
            "education",
            "institution",
            "skills_description",
            "projects_description",
            "research_interests",
            "years_of_experience",
            "website",
            "linkedin",
            "github",
        ]

        widgets = {

            # ==========================================
            # SPECIALIZATION
            # ==========================================

            "specialization": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "Example: Software Development, "
                        "Telecommunications, Physics, AI, "
                        "Research, Engineering..."
                    )
                }
            ),


            # ==========================================
            # DESCRIPTION
            # ==========================================

            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "placeholder": (
                        "Tell us about yourself, what you do, "
                        "your abilities, experience, interests "
                        "and what makes your talent unique..."
                    )
                }
            ),


            # ==========================================
            # EDUCATION
            # ==========================================

            "education": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": (
                        "Tell us about your education, training, "
                        "courses or other learning experiences..."
                    )
                }
            ),


            # ==========================================
            # INSTITUTION
            # ==========================================

            "institution": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "University, company, research institution, "
                        "laboratory, training institution, etc."
                    )
                }
            ),


            # ==========================================
            # SKILLS
            # ==========================================

            "skills_description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": (
                        "Describe your technical, scientific, "
                        "creative, analytical or professional skills..."
                    )
                }
            ),


            # ==========================================
            # PROJECTS
            # ==========================================

            "projects_description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": (
                        "Tell us about projects, inventions, "
                        "research, products, systems or other "
                        "work you have created or contributed to..."
                    )
                }
            ),


            # ==========================================
            # RESEARCH & INNOVATION
            # ==========================================

            "research_interests": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": (
                        "Describe any areas of research, innovation, "
                        "discovery or technology that interest you..."
                    )
                }
            ),


            # ==========================================
            # EXPERIENCE
            # ==========================================

            "years_of_experience": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": 0,
                    "placeholder": "Years of experience"
                }
            ),


            # ==========================================
            # WEBSITE
            # ==========================================

            "website": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "https://example.com"
                }
            ),


            # ==========================================
            # LINKEDIN
            # ==========================================

            "linkedin": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "https://linkedin.com/in/username"
                }
            ),


            # ==========================================
            # GITHUB
            # ==========================================

            "github": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "https://github.com/username"
                }
            ),
        }



from django import forms

from .models import (
    TalentProfile,
    VerificationRequest,
    Achievement,
    Experience,
    Certification,
)

from sports.models import SportsTalentProfile
from science_technology.models import ScienceTechnologyTalentProfile
from art.models import ArtsTalentProfile
from others.models import OtherTalentProfile



# =====================================================
# TALENT PROFILE FORM
# =====================================================

class TalentProfileForm(forms.ModelForm):

    class Meta:

        model = TalentProfile

        fields = [
            "headline",
            "biography",
            "country",
            "city",
            "profile_photo",
            "cover_photo",
            "domains",
            "skills",
            "experience_level",
            "preferred_work_type",
        ]

        widgets = {

            "headline": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "Example: Software Developer | "
                        "Footballer | Musician"
                    ),
                }
            ),

            "biography": forms.Textarea(
                attrs={
                    "rows": 5,
                    "class": "form-control",
                    "placeholder": (
                        "Tell organizations about yourself..."
                    ),
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

            "profile_photo": forms.FileInput(
                attrs={
                    "class": "form-control",
                }
            ),

            "cover_photo": forms.FileInput(
                attrs={
                    "class": "form-control",
                }
            ),

            "domains": forms.SelectMultiple(
                attrs={
                    "class": "form-control",
                }
            ),

            "skills": forms.SelectMultiple(
                attrs={
                    "class": "form-control",
                }
            ),

            "experience_level": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "preferred_work_type": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
        }


# =====================================================
# VERIFICATION REQUEST FORM
# =====================================================

class VerificationRequestForm(forms.ModelForm):

    class Meta:

        model = VerificationRequest

        fields = [
            "document",
            "message",
        ]


# =====================================================
# EXPERIENCE FORM
# =====================================================

class ExperienceForm(forms.ModelForm):

    class Meta:

        model = Experience

        fields = (
            "company",
            "role",
            "description",
            "start_date",
            "end_date",
            "currently_working",
        )

        widgets = {

            "start_date": forms.DateInput(
                attrs={
                    "type": "date",
                }
            ),

            "end_date": forms.DateInput(
                attrs={
                    "type": "date",
                }
            ),
        }


# =====================================================
# CERTIFICATION FORM
# =====================================================

class CertificationForm(forms.ModelForm):

    class Meta:

        model = Certification

        fields = (
            "name",
            "issuing_organization",
            "issue_date",
            "certificate_file",
        )

        widgets = {

            "issue_date": forms.DateInput(
                attrs={
                    "type": "date",
                }
            ),
        }


# =====================================================
# ACHIEVEMENT FORM
# =====================================================

class AchievementForm(forms.ModelForm):

    class Meta:

        model = Achievement

        fields = (
            "title",
            "description",
            "date_received",
            "image",
        )

        widgets = {

            "date_received": forms.DateInput(
                attrs={
                    "type": "date",
                }
            ),
        }


# =====================================================
# TALENT CATEGORY FORM
# =====================================================

class TalentCategoryForm(forms.ModelForm):

    class Meta:

        model = TalentProfile

        fields = [
            "talent_category",
        ]

        widgets = {

            "talent_category": forms.RadioSelect(
                attrs={
                    "class": "talent-category-select",
                }
            ),
        }


# =====================================================
# SPORTS TALENT PROFILE FORM
# =====================================================

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
                    "class": "form-control",
                }
            ),

            "sport_category": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "position": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "Example: Forward, Midfielder, "
                        "Goalkeeper"
                    ),
                }
            ),

            "height": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                    "placeholder": "Example: 1.80",
                }
            ),

            "weight": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                    "placeholder": "Example: 75.00",
                }
            ),

            "bio": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "placeholder": (
                        "Tell organizations about your "
                        "sports background..."
                    ),
                }
            ),
        }


# =====================================================
# SCIENCE & TECHNOLOGY TALENT PROFILE FORM
# =====================================================

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

            "specialization": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "Example: Software Engineering, "
                        "Data Science, Telecommunications"
                    ),
                }
            ),

            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "placeholder": (
                        "Describe your background and "
                        "professional interests..."
                    ),
                }
            ),

            "education": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": (
                        "Describe your educational background..."
                    ),
                }
            ),

            "institution": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "Example: University of Mines and Technology"
                    ),
                }
            ),

            "skills_description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": (
                        "Describe your technical skills..."
                    ),
                }
            ),

            "projects_description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": (
                        "Describe projects you have worked on..."
                    ),
                }
            ),

            "research_interests": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": (
                        "Describe your research interests..."
                    ),
                }
            ),

            "years_of_experience": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "0",
                    "placeholder": "Example: 3",
                }
            ),

            "website": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "https://example.com",
                }
            ),

            "linkedin": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "https://linkedin.com/in/username",
                }
            ),

            "github": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "https://github.com/username",
                }
            ),
        }


# =====================================================
# ARTS TALENT PROFILE FORM
# =====================================================

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

            "specialization": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "Example: Music, Painting, Dance, "
                        "Photography"
                    ),
                }
            ),

            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "placeholder": (
                        "Tell organizations about your artistic "
                        "background..."
                    ),
                }
            ),

            "discipline": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "Example: Afrobeats, Contemporary Dance, "
                        "Digital Art"
                    ),
                }
            ),

            "experience_description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": (
                        "Describe your artistic experience..."
                    ),
                }
            ),

            "years_of_experience": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "0",
                    "placeholder": "Example: 5",
                }
            ),

            "skills_description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": (
                        "Describe your artistic skills..."
                    ),
                }
            ),

            "portfolio_description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": (
                        "Describe your creative portfolio..."
                    ),
                }
            ),

            "achievements_description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": (
                        "Describe your awards and achievements..."
                    ),
                }
            ),

            "creative_interests": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": (
                        "What areas of art are you interested in?"
                    ),
                }
            ),

            "website": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "https://example.com",
                }
            ),

            "portfolio_url": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "https://example.com/portfolio",
                }
            ),

            "instagram": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "https://instagram.com/username",
                }
            ),

            "youtube": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "https://youtube.com/@username",
                }
            ),
        }


# =====================================================
# OTHER TALENT PROFILE FORM
# =====================================================

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

            "specialization": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "Example: Entrepreneurship, "
                        "Public Speaking, Other Talent"
                    ),
                }
            ),

            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "placeholder": (
                        "Tell organizations about yourself..."
                    ),
                }
            ),

            "field": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "Example: Business, Leadership, "
                        "Communication"
                    ),
                }
            ),

            "experience_description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": (
                        "Describe your experience..."
                    ),
                }
            ),

            "years_of_experience": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "0",
                    "placeholder": "Example: 4",
                }
            ),

            "skills_description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": (
                        "Describe your skills..."
                    ),
                }
            ),

            "projects_description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": (
                        "Describe your projects or work..."
                    ),
                }
            ),

            "achievements_description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": (
                        "Describe your achievements..."
                    ),
                }
            ),

            "interests": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": (
                        "What are your areas of interest?"
                    ),
                }
            ),

            "website": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "https://example.com",
                }
            ),

            "linkedin": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "https://linkedin.com/in/username",
                }
            ),

            "other_link": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "https://example.com",
                }
            ),
        }

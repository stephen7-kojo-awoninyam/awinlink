from django import forms
from django.contrib.auth import get_user_model

from .models import (
    Competition,
    CompetitionEvaluation,
    CompetitionJudge,
    CompetitionParticipant,
    CompetitionResult,
)

User = get_user_model()


class CompetitionForm(forms.ModelForm):
    class Meta:
        model = Competition
        fields = (
            "title",
            "description",
            "category",
            "discipline",
            "registration_start",
            "registration_end",
            "competition_start",
            "competition_end",
            "location",
            "online",
            "requirements",
            "prizes",
            "rules",
            "max_participants",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "requirements": forms.Textarea(attrs={"rows": 4}),
            "prizes": forms.Textarea(attrs={"rows": 3}),
            "rules": forms.Textarea(attrs={"rows": 4}),
            "registration_start": forms.DateInput(attrs={"type": "date"}),
            "registration_end": forms.DateInput(attrs={"type": "date"}),
            "competition_start": forms.DateInput(attrs={"type": "date"}),
            "competition_end": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "form-check-input"
            else:
                field.widget.attrs["class"] = "form-control"

    def clean(self):
        cleaned_data = super().clean()
        registration_start = cleaned_data.get("registration_start")
        registration_end = cleaned_data.get("registration_end")
        competition_start = cleaned_data.get("competition_start")
        competition_end = cleaned_data.get("competition_end")

        if registration_start and registration_end:
            if registration_end < registration_start:
                self.add_error(
                    "registration_end",
                    "Registration must end on or after it starts.",
                )
        if competition_start and competition_end:
            if competition_end < competition_start:
                self.add_error(
                    "competition_end",
                    "The competition must end on or after it starts.",
                )
        if registration_end and competition_start:
            if competition_start < registration_end:
                self.add_error(
                    "competition_start",
                    "The competition cannot start before registration closes.",
                )
        return cleaned_data


class SubmissionForm(forms.ModelForm):
    class Meta:
        model = CompetitionParticipant
        fields = ("submission", "submission_url")
        widgets = {
            "submission": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "placeholder": "Describe or submit your work.",
                }
            ),
            "submission_url": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "https://",
                }
            ),
        }


class JudgeAssignmentForm(forms.Form):
    coach = forms.ModelChoiceField(
        queryset=User.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    role = forms.ChoiceField(
        choices=CompetitionJudge.ROLE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["coach"].queryset = User.objects.filter(
            role="COACH"
        ).order_by("username")


class EvaluationForm(forms.ModelForm):
    class Meta:
        model = CompetitionEvaluation
        fields = ("score", "feedback")
        widgets = {
            "score": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": 0,
                    "max": 100,
                    "step": "0.01",
                }
            ),
            "feedback": forms.Textarea(
                attrs={"class": "form-control", "rows": 3},
            ),
        }

    def __init__(self, *args, require_score=True, **kwargs):
        super().__init__(*args, **kwargs)
        if require_score:
            self.fields["score"].required = True
        else:
            self.fields.pop("score")

    def clean(self):
        cleaned_data = super().clean()
        if "score" not in self.fields and not cleaned_data.get("feedback", "").strip():
            raise forms.ValidationError(
                "Enter feedback before saving a mentoring note."
            )
        return cleaned_data


class ResultForm(forms.ModelForm):
    class Meta:
        model = CompetitionResult
        fields = ("position", "score", "award")
        widgets = {
            "position": forms.NumberInput(
                attrs={"class": "form-control", "min": 1}
            ),
            "score": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": 0,
                    "max": 100,
                    "step": "0.01",
                }
            ),
            "award": forms.TextInput(attrs={"class": "form-control"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        if not any(
            (
                cleaned_data.get("position"),
                cleaned_data.get("score") is not None,
                cleaned_data.get("award", "").strip(),
            )
        ):
            raise forms.ValidationError(
                "Enter a position, score, or award for this participant."
            )
        return cleaned_data

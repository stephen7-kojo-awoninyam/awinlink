from django import forms
from django.core.exceptions import ValidationError

from .models import (
    Event,
    EventCertificate,
    EventFeedback,
    EventMedia
)


# ==========================================
# EVENT FORM
# ==========================================

class EventForm(forms.ModelForm):

    class Meta:

        model = Event

        fields = [
            "category",
            "title",
            "slug",
            "description",
            "image",
            "event_type",
            "location",
            "online",
            "meeting_link",
            "start_date",
            "end_date",
            "registration_deadline",
            "capacity",
        ]

        widgets = {

            "description": forms.Textarea(
                attrs={
                    "rows": 5,
                    "class": "form-control"
                }
            ),

            "start_date": forms.DateTimeInput(
                attrs={
                    "type": "datetime-local",
                    "class": "form-control"
                }
            ),

            "end_date": forms.DateTimeInput(
                attrs={
                    "type": "datetime-local",
                    "class": "form-control"
                }
            ),

            "registration_deadline": forms.DateTimeInput(
                attrs={
                    "type": "datetime-local",
                    "class": "form-control"
                }
            ),

        }

    def clean(self):

        cleaned_data = super().clean()

        start = cleaned_data.get("start_date")
        end = cleaned_data.get("end_date")
        deadline = cleaned_data.get(
            "registration_deadline"
        )

        if start and end:

            if end <= start:

                raise ValidationError(
                    "End date must be after start date."
                )

        if deadline and start:

            if deadline >= start:

                raise ValidationError(
                    "Registration deadline must be before the event starts."
                )

        return cleaned_data


# ==========================================
# EVENT FEEDBACK
# ==========================================

class EventFeedbackForm(forms.ModelForm):

    class Meta:

        model = EventFeedback

        fields = [
            "rating",
            "comment",
        ]

        widgets = {

            "rating": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": 1,
                    "max": 5
                }
            ),

            "comment": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "placeholder":
                        "Share your experience..."
                }
            ),

        }

    def clean_rating(self):

        rating = self.cleaned_data.get("rating")

        if rating is None:
            raise forms.ValidationError(
                "Rating is required."
            )

        if rating < 1 or rating > 5:

            raise forms.ValidationError(
                "Rating must be between 1 and 5."
            )

        return rating


# ==========================================
# EVENT CERTIFICATE
# ==========================================

class EventCertificateForm(forms.ModelForm):

    class Meta:

        model = EventCertificate

        fields = [
            "certificate_title",
            "description",
        ]

        widgets = {

            "certificate_title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder":
                        "Certificate of Participation"
                }
            ),

            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder":
                        "Certificate description"
                }
            ),

        }


# ==========================================
# EVENT MEDIA
# ==========================================

class EventMediaForm(forms.ModelForm):

    class Meta:

        model = EventMedia

        fields = [
            "media_type",
            "file",
            "caption",
        ]

        widgets = {

            "media_type": forms.Select(
                attrs={
                    "class": "form-control"
                }
            ),

            "file": forms.ClearableFileInput(
                attrs={
                    "class": "form-control"
                }
            ),

            "caption": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder":
                        "Describe this photo or video"
                }
            ),

        }
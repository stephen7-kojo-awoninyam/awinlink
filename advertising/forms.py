from django import forms
from django.conf import settings
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError

from .models import Advertisement, Campaign


class CampaignForm(forms.ModelForm):
    target_categories = forms.MultipleChoiceField(
        choices=Campaign.CATEGORY_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Campaign
        fields = (
            "name",
            "start_date",
            "end_date",
            "billing_model",
            "total_budget",
            "daily_budget",
            "cost_per_thousand_impressions",
            "cost_per_click",
            "target_categories",
            "domains",
            "sports",
            "skills",
            "frequency_cap",
            "frequency_window_hours",
        )
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "domains": forms.SelectMultiple(attrs={"class": "form-select"}),
            "sports": forms.SelectMultiple(attrs={"class": "form-select"}),
            "skills": forms.SelectMultiple(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.instance.currency = getattr(
                settings,
                "ADVERTISING_CURRENCY",
                "GHS",
            )
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxSelectMultiple):
                field.widget.attrs.setdefault("class", "form-control")
        self.fields["domains"].required = False
        self.fields["sports"].required = False
        self.fields["skills"].required = False

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        if start_date and end_date and end_date < start_date:
            self.add_error("end_date", "End date must be on or after the start date.")

        total_budget = cleaned_data.get("total_budget")
        daily_budget = cleaned_data.get("daily_budget")
        if total_budget is not None and total_budget <= 0:
            self.add_error("total_budget", "Budget must be greater than zero.")
        if (
            total_budget is not None
            and daily_budget is not None
            and daily_budget <= 0
        ):
            self.add_error("daily_budget", "Daily budget must be greater than zero.")
        if (
            total_budget is not None
            and daily_budget is not None
            and daily_budget > total_budget
        ):
            self.add_error("daily_budget", "Daily budget cannot exceed total budget.")
        if cleaned_data.get("frequency_cap", 0) <= 0:
            self.add_error("frequency_cap", "Frequency cap must be at least one.")
        if cleaned_data.get("frequency_window_hours", 0) <= 0:
            self.add_error(
                "frequency_window_hours",
                "Frequency window must be at least one hour.",
            )
        return cleaned_data


class AdvertisementForm(forms.ModelForm):
    class Meta:
        model = Advertisement
        fields = (
            "title",
            "body",
            "image",
            "video",
            "cta_label",
            "destination_url",
        )
        widgets = {
            "body": forms.Textarea(attrs={"rows": 4}),
            "image": forms.ClearableFileInput(attrs={"accept": "image/*"}),
            "video": forms.ClearableFileInput(attrs={"accept": "video/*"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
        self.fields["image"].required = False
        self.fields["video"].required = False

    def clean_destination_url(self):
        destination_url = self.cleaned_data["destination_url"]
        URLValidator(schemes=("https",))(destination_url)
        return destination_url

    def clean(self):
        cleaned_data = super().clean()
        for field_name, max_size, label in (
            ("image", 10 * 1024 * 1024, "Image"),
            ("video", 100 * 1024 * 1024, "Video"),
        ):
            uploaded_file = cleaned_data.get(field_name)
            if uploaded_file and uploaded_file.size > max_size:
                self.add_error(
                    field_name,
                    f"{label} must be no larger than {max_size // (1024 * 1024)} MB.",
                )

        existing_image = bool(self.instance.pk and self.instance.image)
        existing_video = bool(self.instance.pk and self.instance.video)
        if not any(
            (
                cleaned_data.get("image"),
                cleaned_data.get("video"),
                existing_image,
                existing_video,
                cleaned_data.get("body"),
            )
        ):
            raise ValidationError(
                "Add ad copy or upload an image or video for the advertisement."
            )
        if cleaned_data.get("image") and cleaned_data.get("video"):
            raise ValidationError("Upload either an image or a video, not both.")
        return cleaned_data

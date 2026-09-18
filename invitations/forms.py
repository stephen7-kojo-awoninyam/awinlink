from django import forms
from .models import Invitation


class InvitationForm(forms.ModelForm):

    class Meta:

        model = Invitation


        fields = [
            "opportunity",
            "message",
        ]


        widgets = {

            "message": forms.Textarea(

                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Write a message to the talent..."
                }

            ),

        }
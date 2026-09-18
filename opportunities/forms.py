from django import forms
from .models import Opportunity

class OpportunityForm(forms.ModelForm):


    class Meta:


        model = Opportunity


        fields = [

            "title",

            "opportunity_type",

            "domain",

            "skills",

            "description",

            "experience_level",

            "work_type",

            "location",

            "deadline",

            "active",

        ]


        widgets = {

            "title": forms.TextInput(
                attrs={
                    "class": "form-control"
                }
            ),


            "opportunity_type": forms.Select(
                attrs={
                    "class": "form-control"
                }
            ),


            "domain": forms.Select(
                attrs={
                    "class": "form-control"
                }
            ),


            "skills": forms.SelectMultiple(
                attrs={
                    "class": "form-control"
                }
            ),


            "experience_level": forms.Select(
                attrs={
                    "class": "form-control"
                }
            ),


            "work_type": forms.Select(
                attrs={
                    "class": "form-control"
                }
            ),


            "location": forms.TextInput(
                attrs={
                    "class": "form-control"
                }
            ),


            "deadline": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date"
                }
            ),


            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5
                }
            ),
        }



    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)


        self.fields["skills"].widget.attrs.update(

            {

                "class": "form-control"

            }

        )


        self.fields["skills"].widget.attrs["size"] = 5
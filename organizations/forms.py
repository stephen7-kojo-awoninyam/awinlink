from django import forms

from .models import Organization



class OrganizationForm(forms.ModelForm):


    class Meta:

        model = Organization


        fields = [

            "name",

            "category",

            "domain",

            "country",

            "city",

            "headquarters",

            "founded_year",

            "organization_size",

            "level",

            "website",

            "email",

            "phone",

            "description",

            "logo",

        ]



        widgets = {


            "name": forms.TextInput(

                attrs={

                    "class": "form-control",

                    "placeholder": "Organization name"

                }

            ),



            "category": forms.Select(

                attrs={

                    "class": "form-select"

                }

            ),



            "domain": forms.Select(

                attrs={

                    "class": "form-select"

                }

            ),



            "country": forms.TextInput(

                attrs={

                    "class": "form-control",

                    "placeholder": "Country"

                }

            ),



            "city": forms.TextInput(

                attrs={

                    "class": "form-control",

                    "placeholder": "City"

                }

            ),



            "headquarters": forms.TextInput(

                attrs={

                    "class": "form-control",

                    "placeholder": "Headquarters location"

                }

            ),



            "founded_year": forms.NumberInput(

                attrs={

                    "class": "form-control",

                    "placeholder": "Founded year"

                }

            ),



            "organization_size": forms.Select(

                attrs={

                    "class": "form-select"

                }

            ),



            "level": forms.Select(

                attrs={

                    "class": "form-select"

                }

            ),



            "website": forms.URLInput(

                attrs={

                    "class": "form-control",

                    "placeholder": "https://example.com"

                }

            ),



            "email": forms.EmailInput(

                attrs={

                    "class": "form-control",

                    "placeholder": "organization@email.com"

                }

            ),



            "phone": forms.TextInput(

                attrs={

                    "class": "form-control",

                    "placeholder": "+233..."

                }

            ),



            "description": forms.Textarea(

                attrs={

                    "class": "form-control",

                    "rows": 5,

                    "placeholder": "Tell us about your organization"

                }

            ),



            "logo": forms.ClearableFileInput(

                attrs={

                    "class": "form-control"

                }

            ),

        }
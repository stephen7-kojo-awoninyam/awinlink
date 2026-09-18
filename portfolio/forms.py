from django import forms

from .models import PortfolioItem



class PortfolioItemForm(forms.ModelForm):


    class Meta:

        model = PortfolioItem


        fields = (

            "title",

            "description",

            "item_type",
            
            "image",

            "file",

            "link",

        )
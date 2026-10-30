from django import forms

from .models import PortfolioItem
from .permissions import OWNERSHIP_FIELDS



class PortfolioItemForm(forms.ModelForm):

    def clean(self):
        data = super().clean()
        if OWNERSHIP_FIELDS.intersection(self.data):
            raise forms.ValidationError('Portfolio ownership cannot be changed here.')
        return data


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

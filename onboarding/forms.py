from django import forms

ROLE_CHOICES = (
    ("TALENT", "Talent"),
    ("ORGANIZATION", "Organization"),
    ("COACH", "Coach"),
    ("SCOUT", "Scout"),
)


class RoleSelectionForm(forms.Form):

    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        widget=forms.RadioSelect
    )
from django import forms
from accounts.roles import PUBLIC_ROLE_CHOICES, validate_public_authority_input

ROLE_CHOICES = PUBLIC_ROLE_CHOICES


class RoleSelectionForm(forms.Form):

    def __init__(self, data=None, *args, **kwargs):
        # Keep the legacy web button compatible with the canonical account role.
        if data is not None:
            data = data.copy()
            if data.get('role') == 'TALENT':
                data['role'] = 'ATHLETE'
        super().__init__(data, *args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        validate_public_authority_input(self.data)
        return cleaned

    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        widget=forms.RadioSelect
    )

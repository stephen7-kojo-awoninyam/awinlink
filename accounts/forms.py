from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError

import phonenumbers
from phonenumbers import NumberParseException
from phonenumbers.phonenumberutil import region_code_for_country_code
from phonenumbers.phonenumberutil import country_code_for_region

from .models import User


# ---------------------------------------------------------
# COUNTRY LIST
# ---------------------------------------------------------

COUNTRIES = [
    ("AF", "Afghanistan"),
    ("AL", "Albania"),
    ("DZ", "Algeria"),
    ("AD", "Andorra"),
    ("AO", "Angola"),
    ("AG", "Antigua and Barbuda"),
    ("AR", "Argentina"),
    ("AM", "Armenia"),
    ("AU", "Australia"),
    ("AT", "Austria"),
    ("AZ", "Azerbaijan"),
    ("BS", "Bahamas"),
    ("BH", "Bahrain"),
    ("BD", "Bangladesh"),
    ("BB", "Barbados"),
    ("BY", "Belarus"),
    ("BE", "Belgium"),
    ("BZ", "Belize"),
    ("BJ", "Benin"),
    ("BT", "Bhutan"),
    ("BO", "Bolivia"),
    ("BA", "Bosnia and Herzegovina"),
    ("BW", "Botswana"),
    ("BR", "Brazil"),
    ("BN", "Brunei"),
    ("BG", "Bulgaria"),
    ("BF", "Burkina Faso"),
    ("BI", "Burundi"),
    ("CV", "Cabo Verde"),
    ("KH", "Cambodia"),
    ("CM", "Cameroon"),
    ("CA", "Canada"),
    ("CF", "Central African Republic"),
    ("TD", "Chad"),
    ("CL", "Chile"),
    ("CN", "China"),
    ("CO", "Colombia"),
    ("KM", "Comoros"),
    ("CG", "Congo"),
    ("CD", "Democratic Republic of the Congo"),
    ("CR", "Costa Rica"),
    ("CI", "Côte d'Ivoire"),
    ("HR", "Croatia"),
    ("CU", "Cuba"),
    ("CY", "Cyprus"),
    ("CZ", "Czech Republic"),
    ("DK", "Denmark"),
    ("DJ", "Djibouti"),
    ("DM", "Dominica"),
    ("DO", "Dominican Republic"),
    ("EC", "Ecuador"),
    ("EG", "Egypt"),
    ("SV", "El Salvador"),
    ("GQ", "Equatorial Guinea"),
    ("ER", "Eritrea"),
    ("EE", "Estonia"),
    ("SZ", "Eswatini"),
    ("ET", "Ethiopia"),
    ("FJ", "Fiji"),
    ("FI", "Finland"),
    ("FR", "France"),
    ("GA", "Gabon"),
    ("GM", "Gambia"),
    ("GE", "Georgia"),
    ("DE", "Germany"),
    ("GH", "Ghana"),
    ("GR", "Greece"),
    ("GD", "Grenada"),
    ("GT", "Guatemala"),
    ("GN", "Guinea"),
    ("GW", "Guinea-Bissau"),
    ("GY", "Guyana"),
    ("HT", "Haiti"),
    ("HN", "Honduras"),
    ("HU", "Hungary"),
    ("IS", "Iceland"),
    ("IN", "India"),
    ("ID", "Indonesia"),
    ("IR", "Iran"),
    ("IQ", "Iraq"),
    ("IE", "Ireland"),
    ("IL", "Israel"),
    ("IT", "Italy"),
    ("JM", "Jamaica"),
    ("JP", "Japan"),
    ("JO", "Jordan"),
    ("KZ", "Kazakhstan"),
    ("KE", "Kenya"),
    ("KI", "Kiribati"),
    ("KP", "North Korea"),
    ("KR", "South Korea"),
    ("KW", "Kuwait"),
    ("KG", "Kyrgyzstan"),
    ("LA", "Laos"),
    ("LV", "Latvia"),
    ("LB", "Lebanon"),
    ("LS", "Lesotho"),
    ("LR", "Liberia"),
    ("LY", "Libya"),
    ("LI", "Liechtenstein"),
    ("LT", "Lithuania"),
    ("LU", "Luxembourg"),
    ("MG", "Madagascar"),
    ("MW", "Malawi"),
    ("MY", "Malaysia"),
    ("MV", "Maldives"),
    ("ML", "Mali"),
    ("MT", "Malta"),
    ("MH", "Marshall Islands"),
    ("MR", "Mauritania"),
    ("MU", "Mauritius"),
    ("MX", "Mexico"),
    ("FM", "Micronesia"),
    ("MD", "Moldova"),
    ("MC", "Monaco"),
    ("MN", "Mongolia"),
    ("ME", "Montenegro"),
    ("MA", "Morocco"),
    ("MZ", "Mozambique"),
    ("MM", "Myanmar"),
    ("NA", "Namibia"),
    ("NR", "Nauru"),
    ("NP", "Nepal"),
    ("NL", "Netherlands"),
    ("NZ", "New Zealand"),
    ("NI", "Nicaragua"),
    ("NE", "Niger"),
    ("NG", "Nigeria"),
    ("MK", "North Macedonia"),
    ("NO", "Norway"),
    ("OM", "Oman"),
    ("PK", "Pakistan"),
    ("PW", "Palau"),
    ("PS", "Palestine"),
    ("PA", "Panama"),
    ("PG", "Papua New Guinea"),
    ("PY", "Paraguay"),
    ("PE", "Peru"),
    ("PH", "Philippines"),
    ("PL", "Poland"),
    ("PT", "Portugal"),
    ("QA", "Qatar"),
    ("RO", "Romania"),
    ("RU", "Russia"),
    ("RW", "Rwanda"),
    ("KN", "Saint Kitts and Nevis"),
    ("LC", "Saint Lucia"),
    ("VC", "Saint Vincent and the Grenadines"),
    ("WS", "Samoa"),
    ("SM", "San Marino"),
    ("ST", "Sao Tome and Principe"),
    ("SA", "Saudi Arabia"),
    ("SN", "Senegal"),
    ("RS", "Serbia"),
    ("SC", "Seychelles"),
    ("SL", "Sierra Leone"),
    ("SG", "Singapore"),
    ("SK", "Slovakia"),
    ("SI", "Slovenia"),
    ("SB", "Solomon Islands"),
    ("SO", "Somalia"),
    ("ZA", "South Africa"),
    ("SS", "South Sudan"),
    ("ES", "Spain"),
    ("LK", "Sri Lanka"),
    ("SD", "Sudan"),
    ("SR", "Suriname"),
    ("SE", "Sweden"),
    ("CH", "Switzerland"),
    ("SY", "Syria"),
    ("TW", "Taiwan"),
    ("TJ", "Tajikistan"),
    ("TZ", "Tanzania"),
    ("TH", "Thailand"),
    ("TL", "Timor-Leste"),
    ("TG", "Togo"),
    ("TO", "Tonga"),
    ("TT", "Trinidad and Tobago"),
    ("TN", "Tunisia"),
    ("TR", "Türkiye"),
    ("TM", "Turkmenistan"),
    ("TV", "Tuvalu"),
    ("UG", "Uganda"),
    ("UA", "Ukraine"),
    ("AE", "United Arab Emirates"),
    ("GB", "United Kingdom"),
    ("US", "United States"),
    ("UY", "Uruguay"),
    ("UZ", "Uzbekistan"),
    ("VU", "Vanuatu"),
    ("VA", "Vatican City"),
    ("VE", "Venezuela"),
    ("VN", "Vietnam"),
    ("YE", "Yemen"),
    ("ZM", "Zambia"),
    ("ZW", "Zimbabwe"),
]


class UserRegistrationForm(UserCreationForm):

    email = forms.EmailField(
        required=True,
        label="Email address",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "you@example.com",
                "autocomplete": "email",
            }
        ),
    )

    country = forms.ChoiceField(
        required=True,
        choices=[("", "Select your country")] + COUNTRIES,
        widget=forms.Select(
            attrs={
                "class": "form-select",
                "id": "id_country",
            }
        ),
    )

    phone_number = forms.CharField(
        required=True,
        label="Phone number",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter your phone number",
                "autocomplete": "tel",
                "id": "id_phone_number",
            }
        ),
    )

    username = forms.CharField(
        required=True,
        label="Username",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Choose a unique username",
                "autocomplete": "username",
                "id": "id_username",
            }
        ),
    )

    # Organization-only fields
    organization_name = forms.CharField(
        required=False,
        label="Organization Name",
    )
    
    
    organization_username = forms.CharField(
    required=False,
    label="Organization Username",
    widget=forms.TextInput(
        attrs={
            "class": "form-control",
            "placeholder": "Choose a unique organization username",
            "autocomplete": "off",
        }
    ),
)

    organization_email = forms.EmailField(
        required=False,
        label="Organization Email",
    )

    website = forms.URLField(
        required=False,
        label="Website",
    )

    class Meta:
        model = User
        fields = (
            "first_name",
            "last_name",
            "username",
            "email",
            "phone_number",
            "country",
            "role",
            "organization_username",
            "password1",
            "password2",
        )

    # -----------------------------------------------------
    # USERNAME VALIDATION
    # -----------------------------------------------------

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()

        if not username:
            raise ValidationError("Please enter a username.")

        # Remove accidental @ symbol if user enters @username.
        username = username.lstrip("@")

        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError(
                "This username is already taken. Please choose another one."
            )

        return username
    
    def clean_organization_username(self):  
        organization_username = (
        self.cleaned_data.get("organization_username", "")
        .strip()
        .lower()
        )

        if not organization_username:
            return organization_username

        # Remove accidental @ symbol.
        organization_username = organization_username.lstrip("@")

        if User.objects.filter(
        organization_username__iexact=organization_username
        ).exists():
                raise ValidationError(
                "This organization username is already taken. "
                "Please choose another one."
                )

        return organization_username

    # -----------------------------------------------------
    # EMAIL VALIDATION
    # -----------------------------------------------------

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()

        if not email:
            raise ValidationError("Please enter your email address.")

        return email

    # -----------------------------------------------------
    # PHONE VALIDATION
    # -----------------------------------------------------

    def clean_phone_number(self):
        phone = self.cleaned_data.get("phone_number", "").strip()
        country = self.cleaned_data.get("country")

        if not phone:
            raise ValidationError("Please enter your phone number.")

        if not country:
            raise ValidationError(
                "Please select your country before entering your phone number."
            )

        try:
            parsed_number = phonenumbers.parse(
                phone,
                country
            )

        except NumberParseException:
            raise ValidationError(
                "Please enter a valid phone number for your selected country."
            )

        if not phonenumbers.is_valid_number(parsed_number):
            raise ValidationError(
                "This phone number is not valid for the selected country."
            )

        # Store the phone number in international format.
        return phonenumbers.format_number(
            parsed_number,
            phonenumbers.PhoneNumberFormat.E164
        )

    # -----------------------------------------------------
    # ORGANIZATION VALIDATION
    # -----------------------------------------------------

    def clean(self):

        cleaned_data = super().clean()

        role = cleaned_data.get("role")

        if role == "ORGANIZATION":

            organization_name = cleaned_data.get("organization_name")
            organization_username = cleaned_data.get("organization_username")
            organization_email = cleaned_data.get("organization_email")

            if not organization_name:
                self.add_error(
                    "organization_name",
                    "Organization name is required."
                )
                
            if not organization_username:
                self.add_error(
                    "organization_username",
                    "Organization username is required."
                )
        

            if not organization_email:
                self.add_error(
                    "organization_email",
                    "Organization email is required."
                )

        return cleaned_data


class LoginForm(AuthenticationForm):
    pass
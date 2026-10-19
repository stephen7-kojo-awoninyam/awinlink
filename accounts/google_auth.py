"""Google authorization-code OIDC; no email-based authentication or linking."""
import base64
import hashlib
import secrets
from datetime import timedelta
from functools import wraps
from urllib.parse import urlencode, urlsplit

import httpx
import jwt
from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .forms import UserRegistrationForm
from .models import GoogleAuthAttempt, GoogleIdentity, User

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
JWKS = jwt.PyJWKClient("https://www.googleapis.com/oauth2/v3/certs", timeout=5)


class GoogleAuthError(Exception):
    pass


def private_response(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        response = view(*args, **kwargs)
        response["Cache-Control"] = "no-store"
        response["Referrer-Policy"] = "no-referrer"
        return response
    return wrapped


def configuration():
    client = settings.GOOGLE_OAUTH_CLIENT_ID
    secret = settings.GOOGLE_OAUTH_CLIENT_SECRET
    callback = settings.GOOGLE_OAUTH_REDIRECT_URI
    parsed = urlsplit(callback)
    local = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}
    if not client or not secret or not parsed.netloc or parsed.query or parsed.fragment or parsed.username or (parsed.scheme != "https" and not local):
        raise GoogleAuthError("Google sign-in is not configured. Use your existing sign-in method.")
    return client, secret, callback


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def begin(*, mobile=False, link_user=None):
    client, _, callback = configuration()
    mobile_secret = secrets.token_urlsafe(32) if mobile else ""
    attempt = GoogleAuthAttempt.objects.create(
        state=secrets.token_urlsafe(32), nonce=secrets.token_urlsafe(32), verifier=secrets.token_urlsafe(64),
        mobile_secret_hash=digest(mobile_secret) if mobile else "", link_user=link_user,
        expires_at=timezone.now() + timedelta(minutes=10),
    )
    challenge = base64.urlsafe_b64encode(hashlib.sha256(attempt.verifier.encode()).digest()).rstrip(b"=").decode()
    url = AUTHORIZE_URL + "?" + urlencode(dict(client_id=client, redirect_uri=callback,
        response_type="code", scope="openid email profile", state=attempt.state, nonce=attempt.nonce,
        code_challenge=challenge, code_challenge_method="S256", prompt="select_account"))
    return attempt, url, mobile_secret


def validate_id_token(token, nonce):
    client, _, _ = configuration()
    try:
        key = JWKS.get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"], audience=client,
            issuer=["https://accounts.google.com", "accounts.google.com"],
            options={"require": ["iss", "aud", "exp", "iat", "sub", "nonce", "email", "email_verified"]})
        audiences = claims["aud"] if isinstance(claims["aud"], list) else [claims["aud"]]
        if (claims.get("azp", client) != client or (len(audiences) > 1 and claims.get("azp") != client)
            or not isinstance(claims["nonce"], str) or not secrets.compare_digest(claims["nonce"], nonce)
            or claims["email_verified"] is not True or not isinstance(claims["sub"], str)
            or not claims["sub"] or len(claims["sub"]) > 255):
            raise ValueError("Invalid identity claims")
        forms.EmailField().clean(claims["email"])
        return {"sub": claims["sub"], "email": claims["email"],
            "given_name": str(claims.get("given_name", ""))[:150], "family_name": str(claims.get("family_name", ""))[:150]}
    except (jwt.PyJWTError, ValueError, TypeError, KeyError, ValidationError) as exc:
        raise GoogleAuthError("Google identity could not be verified. Start sign-in again.") from exc


def exchange(state, code):
    # Claim the callback before network I/O so concurrent/replayed codes cannot authenticate twice.
    with transaction.atomic():
        attempt = GoogleAuthAttempt.objects.select_for_update().filter(state=state).first()
        if not attempt or attempt.status != "PENDING" or attempt.expires_at <= timezone.now():
            raise GoogleAuthError("This Google sign-in has expired or was already used.")
        if not GoogleAuthAttempt.objects.filter(pk=attempt.pk, status="PENDING").update(status="EXCHANGING"):
            raise GoogleAuthError("This Google sign-in was already used.")
    try:
        client, secret, callback = configuration()
        response = httpx.post(TOKEN_URL, data=dict(code=code, client_id=client, client_secret=secret,
            redirect_uri=callback, grant_type="authorization_code", code_verifier=attempt.verifier), timeout=10)
        response.raise_for_status()
        claims = validate_id_token(response.json()["id_token"], attempt.nonce)
    except (GoogleAuthError, httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        GoogleAuthAttempt.objects.filter(pk=attempt.pk).update(status="FAILED", verifier="", nonce="")
        raise GoogleAuthError("Google sign-in failed. Start again or use your existing sign-in method.") from exc
    GoogleAuthAttempt.objects.filter(pk=attempt.pk).update(status="VERIFIED", claims=claims, verifier="", nonce="")
    attempt.refresh_from_db()
    return attempt


class GoogleSignupForm(UserRegistrationForm):
    """Retain role, phone, organization and Terms validation without asking for a password."""
    def __init__(self, *args, claims, **kwargs):
        super().__init__(*args, **kwargs)
        self.claims = claims
        self.fields.pop("password1")
        self.fields.pop("password2")
        self.fields["email"].disabled = True
        self.initial["email"] = claims["email"]

    def clean_email(self):
        return self.claims["email"].strip().lower()

    def save(self, commit=True):
        user = forms.ModelForm.save(self, commit=False)
        user.set_unusable_password()
        user.terms_accepted_version = self.cleaned_data["terms_version"]
        user.terms_accepted_at = timezone.now()
        if commit:
            user.save()
            self.save_m2m()
        return user


def complete(attempt, signup=None):
    """Caller must hold the attempt row lock and transaction until consumption/token issuance."""
    if attempt.status != "VERIFIED" or attempt.expires_at <= timezone.now():
        raise GoogleAuthError("This Google sign-in has expired or was already used.")
    subject = attempt.claims["sub"]
    identity = GoogleIdentity.objects.select_related("user").filter(subject=subject).first()
    if attempt.link_user_id:
        user = User.objects.select_for_update().get(pk=attempt.link_user_id)
        if not user.is_active or (identity and identity.user_id != user.pk) or GoogleIdentity.objects.filter(user=user).exclude(subject=subject).exists():
            raise GoogleAuthError("This Google identity cannot be linked to this account.")
        if not identity:
            GoogleIdentity.objects.create(user=user, subject=subject)
    elif identity:
        user = identity.user
        if not user.is_active:
            raise GoogleAuthError("This account is unavailable. Contact support.")
    else:
        if User.objects.filter(email__iexact=attempt.claims["email"]).exists():
            raise GoogleAuthError("Use your existing Awinlink sign-in, then explicitly link Google from your account. Email matches never link accounts automatically.")
        form = GoogleSignupForm(signup, claims=attempt.claims)
        if signup is None or not form.is_valid():
            return None, form
        user = form.save()
        from talents.models import TalentProfile
        from organizations.models import Organization
        if user.role == "ATHLETE":
            TalentProfile.objects.create(user=user)
        elif user.role == "ORGANIZATION":
            Organization.objects.create(user=user, name=form.cleaned_data["organization_name"],
                email=form.cleaned_data["organization_email"], website=form.cleaned_data.get("website", ""),
                phone=user.phone_number, country=user.country)
        GoogleIdentity.objects.create(user=user, subject=subject)
    attempt.status = "CONSUMED"
    attempt.claims = {}
    attempt.save(update_fields=["status", "claims"])
    return user, None

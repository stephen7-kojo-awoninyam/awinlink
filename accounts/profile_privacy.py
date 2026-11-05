"""Redact structured minor data in HTML without changing stored profiles or owner forms."""
import copy

from django.db.models import Model, QuerySet
from django.db.models.query import ModelIterable
from django.http import Http404
from django.shortcuts import render as django_render

from .age_safety import can_view_private_data, minor, visible_users_for
from .models import User

SENSITIVE_FIELDS = {"country", "city", "address", "location", "phone", "phone_number", "email",
                    "date_of_birth", "birth_date", "first_name", "last_name", "biography", "school", "education",
                    "website", "linkedin", "github", "portfolio_url", "instagram", "youtube", "other_link"}


def profile_owner(obj):
    owner = obj if isinstance(obj, User) else getattr(obj, "user", None)
    if owner is None and getattr(obj, "talent_id", None):
        owner = obj.talent.user
    return owner


def safe_profile(obj, viewer):
    owner = profile_owner(obj)
    if not isinstance(owner, User) or not minor(owner) or can_view_private_data(viewer, owner):
        return obj
    if not visible_users_for(viewer).filter(pk=owner.pk).exists():
        return None
    safe = copy.copy(obj)
    safe._state = copy.copy(obj._state)
    safe._state.fields_cache = obj._state.fields_cache.copy()
    for field in obj._meta.concrete_fields:
        if field.name in SENSITIVE_FIELDS:
            setattr(safe, field.name, None if field.null else "")
    if not isinstance(obj, User):
        if any(field.name == "user" for field in obj._meta.fields):
            safe.user = safe_profile(owner, viewer)
        elif getattr(obj, "talent_id", None):
            safe.talent = safe_profile(obj.talent, viewer)
    return safe


def render(request, template_name, context=None, **kwargs):
    result = {}
    for key, value in (context or {}).items():
        if isinstance(value, Model):
            result[key] = safe_profile(value, request.user)
            if result[key] is None and key in {"talent", "profile", "coach", "scout", "athlete", "organization"}:
                raise Http404
        elif isinstance(value, (QuerySet, list, tuple)) and not isinstance(value, str):
            # Only profile collections; retain lazy unrelated querysets and pagination behavior.
            model = getattr(value, "model", None)
            if model and model._meta.model_name in {"talentprofile", "coachprofile", "scoutprofile", "athleteprofile", "user"}:
                field = "pk" if model is User else "user_id"
                value = value.filter(**{field + "__in": visible_users_for(request.user).values("pk")})
                class SafeProfileIterable(ModelIterable):
                    def __iter__(self):
                        for item in super().__iter__():
                            yield safe_profile(item, request.user)
                value._iterable_class = SafeProfileIterable
                result[key] = value
            else:
                result[key] = value
        else:
            result[key] = value
    return django_render(request, template_name, result, **kwargs)


class MinorProfileSerializerMixin:
    def to_representation(self, instance):
        data = super().to_representation(instance)
        owner = profile_owner(instance)
        viewer = getattr(self.context.get("request"), "user", None)
        if isinstance(owner, User) and minor(owner) and not can_view_private_data(viewer, owner):
            for key in SENSITIVE_FIELDS:
                if key in data:
                    data[key] = ""
            if "full_name" in data:
                data["full_name"] = owner.username
        return data

from django.contrib.auth.decorators import login_required
from itertools import islice
from django import forms
from django.shortcuts import redirect, render
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from organizations.models import Organization
from organizations.permissions import organizations_for_capability, OrganizationCapability as Cap
from skills.models import Skill
from talents.models import TalentProfile
from .interest_learning import is_sensitive_topic
from .models import RisingTalentPreference as Preference
from .rising_talent import CATEGORIES, assess, eligible_talents, matches_for, preference_for, recipient_profile, set_preferences


class PreferenceInput(serializers.Serializer):
    discovery_enabled = serializers.BooleanField(required=False)
    alerts_enabled = serializers.BooleanField(required=False)
    category = serializers.ChoiceField(choices=["", *CATEGORIES], required=False)
    skills = serializers.PrimaryKeyRelatedField(queryset=Skill.objects.all(), many=True, required=False)
    organization = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all(), allow_null=True, required=False)

    def validate(self, values):
        user = self.context["user"]
        current = preference_for(user)
        skills = values.get("skills", list(current.skills.all()) if current else [])
        if "skills" in values and (len(skills) > 50 or any(is_sensitive_topic(skill.name) for skill in skills)):
            raise serializers.ValidationError({"skills": "Choose up to 50 non-sensitive skills."})
        proposed = Preference(user=user, category=values.get("category", current.category if current else ""),
            organization=values.get("organization", current.organization if current else None))
        if values.get("discovery_enabled"):
            if not TalentProfile.objects.filter(user=user, user__role="ATHLETE", user__is_active=True,
                    profile_visibility="PUBLIC", talent_category__in=CATEGORIES).exists():
                raise serializers.ValidationError({"discovery_enabled": "Discovery requires your active, public talent profile."})
        if values.get("alerts_enabled") or (current and current.alerts_enabled
                and "alerts_enabled" not in values and any(key in values for key in ("category", "skills", "organization"))):
            if not proposed.category or not skills or not recipient_profile(user, proposed):
                raise serializers.ValidationError({"alerts_enabled": "Choose a category and skills with an active coach, scout or authorized organization profile."})
        if "organization" in values and proposed.organization_id and not organizations_for_capability(user, Cap.VIEW_TALENTS).filter(pk=proposed.organization_id).exists():
            raise serializers.ValidationError({"organization": "Choose an organization you can access."})
        return values


def preference_data(user):
    preference = preference_for(user)
    return {"discovery_enabled": bool(preference and preference.discovery_enabled),
            "alerts_enabled": bool(preference and preference.alerts_enabled),
            "category": preference.category if preference else "",
            "skills": [skill.pk for skill in preference.skills.all()] if preference else [],
            "selected_skills": [{"id": skill.pk, "name": skill.name} for skill in preference.skills.all()] if preference else [],
            "organization": preference.organization_id if preference else None}


def own_assessment(user):
    talent = eligible_talents().filter(user=user).first()
    return assess(talent) if talent else None


class PrivateAPI(APIView):
    permission_classes = [IsAuthenticated]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class PreferencesAPI(PrivateAPI):
    def get(self, request):
        return Response(preference_data(request.user))

    def patch(self, request):
        serializer = PreferenceInput(data=request.data, context={"user": request.user})
        serializer.is_valid(raise_exception=True)
        set_preferences(request.user, serializer.validated_data)
        return Response(preference_data(request.user))


class MatchesAPI(PrivateAPI):
    def get(self, request):
        return Response({"results": matches_for(request.user), "assessment": own_assessment(request.user)})


class OptionsAPI(PrivateAPI):
    def get(self, request):
        query = request.query_params.get("q", "").strip()[:100]
        rows = Skill.objects.filter(name__icontains=query).order_by("name", "pk")
        skills = list(islice(({"id": skill.pk, "name": skill.name} for skill in rows.iterator() if not is_sensitive_topic(skill.name)), 50))
        return Response({"categories": [{"id": key, "name": value} for key, value in CATEGORIES.items()],
            "skills": skills, "organizations": list(organizations_for_capability(request.user, Cap.VIEW_TALENTS).values("id", "name"))})


class RisingPreferencesForm(forms.Form):
    discovery_enabled = forms.BooleanField(required=False, label="Include my public talent profile in Rising Talent")
    alerts_enabled = forms.BooleanField(required=False, label="Notify me about relevant rising talents")
    category = forms.ChoiceField(choices=[("", "Choose a category"), *Preference.CATEGORIES], required=False)
    skills = forms.ModelMultipleChoiceField(queryset=Skill.objects.none(), required=False)
    organization = forms.ModelChoiceField(queryset=Organization.objects.none(), required=False)

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        ids = [skill.pk for skill in Skill.objects.all().iterator() if not is_sensitive_topic(skill.name)]
        self.fields["skills"].queryset = Skill.objects.filter(pk__in=ids).order_by("name", "pk")
        self.fields["organization"].queryset = organizations_for_capability(user, Cap.VIEW_TALENTS)

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        values = {**data, "skills": [skill.pk for skill in data.get("skills", [])],
                  "organization": data["organization"].pk if data.get("organization") else None}
        serializer = PreferenceInput(data=values, context={"user": self.user})
        if not serializer.is_valid():
            raise forms.ValidationError(" ".join(str(message) for messages in serializer.errors.values() for message in messages))
        self.validated_preferences = serializer.validated_data
        return data


@login_required
def rising_page(request):
    if request.method == "POST":
        if request.POST.get("action") == "withdraw":
            set_preferences(request.user, {"discovery_enabled": False, "alerts_enabled": False})
            return redirect("rising_talent")
        form = RisingPreferencesForm(request.POST, user=request.user)
        if form.is_valid():
            set_preferences(request.user, form.validated_preferences)
            return redirect("rising_talent")
    else:
        form = RisingPreferencesForm(user=request.user, initial=preference_data(request.user))
    response = render(request, "recommendations/rising_talent.html", {"form": form,
        "matches": matches_for(request.user), "assessment": own_assessment(request.user)})
    response["Cache-Control"] = "private, no-store"
    return response

"""Scoped guardian approval; no impersonation and no role/organization grants."""
from collections.abc import Mapping
from django import forms
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .age_policy import (
    GUARDIAN_CONSENT_VERSION, PENDING_MESSAGE, account_capabilities,
    approve_guardian, revoke_guardian, validate_birth_date, age_group,
    create_guardian_request,
)
from .models import GuardianAuthorization, User


CONSENT_TEXT = (
    "I am the child's verified adult guardian. I authorize this child's Awinlink account "
    "and accept responsibility for managing it. I understand I can withdraw this authorization."
)


class AgeDetailsForm(forms.Form):
    date_of_birth = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    guardian_email = forms.EmailField(required=False)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_date_of_birth(self):
        return validate_birth_date(self.cleaned_data["date_of_birth"])

    def clean(self):
        data = super().clean()
        if data.get("date_of_birth") and age_group(data["date_of_birth"]) == "CHILD":
            email = data.get("guardian_email", "").strip().lower()
            if not email or email == self.user.email.strip().lower():
                self.add_error("guardian_email", "A separate adult guardian email address is required.")
        return data

    @transaction.atomic
    def save(self):
        user = User.objects.select_for_update().get(pk=self.user.pk)
        if user.date_of_birth is not None:
            raise ValidationError("Date of birth is already recorded. Contact support for corrections.")
        user.date_of_birth = self.cleaned_data["date_of_birth"]
        user.birth_date_source = "ACCOUNT_ONBOARDING"
        if user.age_group == "CHILD":
            user.is_active = False
        user.save(update_fields=["date_of_birth", "birth_date_source", "is_active"])
        create_guardian_request(user, self.cleaned_data)
        return user


def guardian_requests(user):
    from .age_safety import cutoff
    return GuardianAuthorization.objects.filter(guardian=user, verified_at__isnull=False,
                                                child__date_of_birth__gt=cutoff(18)).select_related("child")


def representation(item):
    return {"id": item.pk, "child_username": item.child.username, "status": item.status,
            "verified_at": item.verified_at, "consented_at": item.consented_at,
            "consent_version": GUARDIAN_CONSENT_VERSION, "consent_text": CONSENT_TEXT,
            "contacts": [{"username": grant.contact.username, "allow_calls": grant.allow_calls}
                         for grant in item.contact_permissions.select_related("contact")] if item.status == "APPROVED" else [],
            "courses": [{"course_id": grant.course_id, "title": grant.course.title, "allow_live": grant.allow_live}
                        for grant in item.course_permissions.select_related("course")] if item.status == "APPROVED" else []}


@login_required
@require_http_methods(["GET", "POST"])
def guardian_authorizations(request):
    from learning.models import Course
    from django.db.models import Q
    error = ""
    if request.method == "POST":
        item = get_object_or_404(guardian_requests(request.user), pk=request.POST.get("authorization_id")
                                 if str(request.POST.get("authorization_id", "")).isdigit() else 0)
        try:
            if request.POST.get("action") == "approve":
                approve_guardian(actor=request.user, authorization_id=item.pk,
                                 accepted=request.POST.get("accepted") == "on", version=request.POST.get("version"))
            elif request.POST.get("action") == "revoke":
                revoke_guardian(actor=request.user, authorization_id=item.pk)
            elif request.POST.get("action") in {"allow_contact", "remove_contact", "allow_course", "remove_course"}:
                from .guardian_permissions import change_permission
                change_permission(actor=request.user, authorization_id=item.pk, action=request.POST["action"],
                    data={**request.POST.dict(), "allow_calls": request.POST.get("allow_calls") == "on",
                          "allow_live": request.POST.get("allow_live") == "on"})
            else:
                raise ValidationError("Choose a valid authorization action.")
            return redirect("guardian_authorizations")
        except ValidationError as exc:
            error = " ".join(exc.messages)
    return render(request, "accounts/guardian_authorizations.html", {
        "authorizations": guardian_requests(request.user), "consent_text": CONSENT_TEXT,
        "consent_version": GUARDIAN_CONSENT_VERSION, "error": error,
        "age_unknown": request.user.date_of_birth is None,
        "available_courses": Course.objects.filter(Q(status="APPROVED") | Q(creator_id__in=
            guardian_requests(request.user).filter(status="APPROVED").values("child_id"))).order_by("title"),
    }, status=400 if error else 200)


@login_required
@require_http_methods(["GET", "POST"])
def age_details(request):
    form = AgeDetailsForm(request.POST if request.method == "POST" else None, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            user = form.save()
            if not user.is_active:
                logout(request)
                return render(request, "accounts/guardian_pending.html", status=202)
            return redirect("guardian_authorizations")
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(request, "accounts/age_details.html", {"form": form})


class AgeDetailsAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not isinstance(request.data, Mapping):
            return Response({"detail": "Enter valid age details."}, status=400)
        form = AgeDetailsForm(request.data, user=request.user)
        if not form.is_valid():
            return Response(form.errors, status=400)
        try:
            user = form.save()
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=400)
        return Response({"account_capabilities": account_capabilities(user),
                         **({"guardian_approval_required": True, "detail": PENDING_MESSAGE} if not user.is_active else {})},
                        status=202 if not user.is_active else 200)


class GuardianAuthorizationsAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response([representation(item) for item in guardian_requests(request.user)])

    def post(self, request, authorization_id):
        if not isinstance(request.data, Mapping):
            return Response({"detail": "Enter valid authorization details."}, status=400)
        item = get_object_or_404(guardian_requests(request.user), pk=authorization_id)
        try:
            if request.data.get("action") == "approve":
                item = approve_guardian(actor=request.user, authorization_id=item.pk,
                                        accepted=request.data.get("accepted"), version=request.data.get("version"))
            elif request.data.get("action") == "revoke":
                item = revoke_guardian(actor=request.user, authorization_id=item.pk)
            elif request.data.get("action") in {"allow_contact", "remove_contact", "allow_course", "remove_course"}:
                from .guardian_permissions import change_permission
                item = change_permission(actor=request.user, authorization_id=item.pk,
                                         action=request.data["action"], data=request.data)
            else:
                raise ValidationError("Choose a valid authorization action.")
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=400)
        return Response(representation(item))


class GuardianLearningAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, authorization_id):
        from .age_safety import guardian_of
        from learning.models import Enrollment
        item = get_object_or_404(guardian_requests(request.user), pk=authorization_id)
        if not guardian_of(request.user, item.child):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied("Current guardian authorization is required.")
        return Response([{"course_id": row.course_id, "title": row.course.title,
                          "completed": row.completed, "completed_lessons": row.lesson_progress.filter(completed=True).count(),
                          "lesson_count": row.course.lessons.count()}
                         for row in Enrollment.objects.filter(user=item.child).select_related("course")])


class GuardianCourseCatalogAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, authorization_id):
        from .age_safety import guardian_of
        from django.db.models import Q
        from learning.models import Course
        from api.pagination import BoundedCursorPagination
        item = get_object_or_404(guardian_requests(request.user), pk=authorization_id)
        if not guardian_of(request.user, item.child):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied("Current guardian authorization is required.")
        query = Course.objects.filter(Q(status="APPROVED") | Q(creator=item.child)).order_by("-pk")
        paginator = BoundedCursorPagination()
        page = paginator.paginate_queryset(query, request, view=self)
        return paginator.get_paginated_response([{"id": course.pk, "title": course.title, "minimum_age": course.minimum_age}
                                                for course in page])


@login_required
@require_http_methods(["GET"])
def guardian_learning(request, authorization_id):
    from .age_safety import guardian_of
    from learning.models import Enrollment
    item = get_object_or_404(guardian_requests(request.user), pk=authorization_id)
    if not guardian_of(request.user, item.child):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("Current guardian authorization is required.")
    return render(request, "accounts/guardian_learning.html", {"child": item.child,
        "enrollments": Enrollment.objects.filter(user=item.child).select_related("course")})

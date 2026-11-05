from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils.html import format_html

from .age_policy import verify_guardian
from .models import GuardianAuthorization, GuardianAuditEvent, User


class VerificationForm(forms.Form):
    guardian = forms.ModelChoiceField(queryset=User.objects.filter(is_active=True))
    reference = forms.CharField(max_length=200, help_text="Internal case reference for completed identity, adulthood and guardian relationship checks. Do not enter identity documents here.")
    checked = forms.BooleanField(label="I independently verified this adult's identity, adulthood and relationship to the child.")


@admin.register(GuardianAuthorization)
class GuardianAuthorizationAdmin(admin.ModelAdmin):
    list_display = ["id", "child", "nominated_email", "guardian", "status", "verified_at", "review_link"]
    readonly_fields = [field.name for field in GuardianAuthorization._meta.fields]

    def has_view_permission(self, request, obj=None):
        return super().has_view_permission(request, obj) or request.user.has_perm("accounts.verify_guardianauthorization")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def review_link(self, obj):
        if obj.status == "PENDING" and not obj.verified_at:
            return format_html('<a href="{}">Verify guardian</a>', reverse("admin:accounts_guardian_verify", args=[obj.pk]))
        return ""

    def get_urls(self):
        return [path("<int:authorization_id>/verify/", self.admin_site.admin_view(self.verify), name="accounts_guardian_verify")] + super().get_urls()

    def verify(self, request, authorization_id):
        from django.core.exceptions import PermissionDenied
        if not request.user.has_perm("accounts.verify_guardianauthorization"):
            raise PermissionDenied
        item = get_object_or_404(GuardianAuthorization, pk=authorization_id)
        form = VerificationForm(request.POST if request.method == "POST" else None)
        if request.method == "POST" and form.is_valid():
            try:
                verify_guardian(actor=request.user, authorization_id=item.pk,
                                guardian_id=form.cleaned_data["guardian"].pk, reference=form.cleaned_data["reference"])
                self.message_user(request, "Guardian verified. The guardian must still explicitly approve; the child remains restricted.")
                return redirect("admin:accounts_guardianauthorization_changelist")
            except ValidationError as exc:
                form.add_error(None, exc)
        return render(request, "admin/guardian_verify.html", {
            **self.admin_site.each_context(request), "title": "Verify guardian", "form": form, "authorization": item})


@admin.register(GuardianAuditEvent)
class GuardianAuditEventAdmin(admin.ModelAdmin):
    list_display = ["authorization", "actor", "action", "created_at"]
    readonly_fields = [field.name for field in GuardianAuditEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

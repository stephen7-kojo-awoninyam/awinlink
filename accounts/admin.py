from django.contrib import admin
from .models import ContentReport, UserBlock, ReportReviewEvent
from django import forms
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils.html import format_html
from .report_review import review_report
from django.db.models import Case, IntegerField, Value, When


class ReportReviewForm(forms.Form):
    new_status = forms.ChoiceField(choices=[('REVIEWED', 'Reviewed / reopen'), ('ESCALATED', 'Requires escalation'), ('RESOLVED', 'Resolved')])
    action = forms.ChoiceField(choices=[('REVIEW', 'Record review only'), ('REMOVE_POST', 'Remove reported post and require follow-up')])
    notes = forms.CharField(min_length=10, max_length=2000, widget=forms.Textarea)


@admin.register(ContentReport)
class ContentReportAdmin(admin.ModelAdmin):
    list_display = ['id', 'target_type', 'target_id', 'reason', 'status', 'created_at', 'review_link']
    list_filter = ['status', 'reason', 'target_type']
    readonly_fields = ['reporter', 'target_type', 'target_id', 'reason', 'details', 'contact_email', 'status', 'created_at']
    search_fields = ['details']

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            safety_priority=Case(When(reason='child_safety', then=Value(0)), default=Value(1), output_field=IntegerField()),
            closed_priority=Case(When(status='RESOLVED', then=Value(1)), default=Value(0), output_field=IntegerField()),
        ).order_by('closed_priority', 'safety_priority', 'created_at', 'pk')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm('accounts.view_contentreport') or request.user.has_perm('accounts.change_contentreport')

    def has_delete_permission(self, request, obj=None):
        return False

    def review_link(self, obj):
        return format_html('<a href="{}">Review / escalate</a>', reverse('admin:accounts_report_review', args=[obj.pk]))

    def get_urls(self):
        return [path('<int:report_id>/review/', self.admin_site.admin_view(self.review), name='accounts_report_review')] + super().get_urls()

    def review(self, request, report_id):
        if not request.user.has_perm('accounts.change_contentreport'):
            raise PermissionDenied
        report = get_object_or_404(ContentReport, pk=report_id)
        form = ReportReviewForm(request.POST if request.method == 'POST' else None)
        if request.method == 'POST' and form.is_valid():
            try:
                review_report(actor=request.user, report_id=report.pk, **form.cleaned_data)
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                self.message_user(request, 'Review recorded. Escalation and storage follow-up require actual operator action.')
                return redirect('admin:accounts_contentreport_changelist')
        return render(request, 'admin/report_review.html', {**self.admin_site.each_context(request),
            'report': report, 'form': form, 'title': 'Review safety report',
            'events': report.review_events.select_related('actor').order_by('created_at', 'pk')})


@admin.register(ReportReviewEvent)
class ReportReviewEventAdmin(admin.ModelAdmin):
    list_display = ['report', 'actor', 'action', 'previous_status', 'new_status', 'created_at']
    readonly_fields = [field.name for field in ReportReviewEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(UserBlock)
class UserBlockAdmin(admin.ModelAdmin):
    list_display = ['user', 'blocked_user', 'created_at']

# Register your models here.
from . import guardian_admin  # noqa: F401

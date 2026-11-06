"""Explicit human review; submission never automatically punishes a reported user."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .models import ContentReport, ReportReviewEvent, User


@transaction.atomic
def review_report(*, actor, report_id, new_status, notes, action='REVIEW'):
    current = User.objects.get(pk=actor.pk)
    if not current.is_active or not current.is_staff or not current.has_perm('accounts.change_contentreport'):
        raise PermissionDenied('Report review permission is required.')
    notes = notes.strip() if isinstance(notes, str) else ''
    if not 10 <= len(notes) <= 2000:
        raise ValidationError('Record a review outcome or escalation case reference (10–2000 characters). Do not include CSAM.')
    report = ContentReport.objects.select_for_update().get(pk=report_id)
    transitions = {'OPEN': {'REVIEWED', 'ESCALATED'}, 'REVIEWED': {'REVIEWED', 'ESCALATED', 'RESOLVED'},
                   'ESCALATED': {'ESCALATED', 'REVIEWED', 'RESOLVED'}, 'RESOLVED': {'REVIEWED'}}
    if new_status not in transitions.get(report.status, set()):
        raise ValidationError('Review before resolving, or reopen a resolved report for review.')
    if action == 'REMOVE_POST':
        if report.target_type != 'post' or not current.has_perm('feed.delete_post'):
            raise PermissionDenied('Removing a reported post requires post deletion permission.')
        if new_status != 'ESCALATED':
            raise ValidationError('Removed posts require escalation for storage/evidence and legal follow-up.')
        from feed.models import Post
        post = Post.objects.select_for_update().filter(pk=report.target_id).first()
        if not post:
            raise ValidationError('The reported post is already unavailable; record a review instead.')
        post.delete()
    elif action != 'REVIEW':
        raise ValidationError('Unknown review action.')
    previous = report.status
    report.status = new_status
    report.save(update_fields=['status'])
    return ReportReviewEvent.objects.create(report=report, actor=current, action=action,
        previous_status=previous, new_status=new_status, notes=notes)

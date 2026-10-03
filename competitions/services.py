from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Competition, CompetitionResult


ALLOWED_TRANSITIONS = {
    "DRAFT": {"SUBMITTED", "CANCELLED"},
    "SUBMITTED": {"APPROVED", "REJECTED", "CANCELLED"},
    "REJECTED": {"DRAFT", "SUBMITTED", "CANCELLED"},
    "APPROVED": {"PUBLISHED", "CANCELLED"},
    "PUBLISHED": {"REGISTRATION_CLOSED", "ONGOING", "CANCELLED"},
    "REGISTRATION_CLOSED": {"ONGOING", "CANCELLED"},
    "ONGOING": {"JUDGING", "CANCELLED"},
    "JUDGING": {"RESULTS", "CANCELLED"},
    "RESULTS": {"COMPLETED", "CANCELLED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
}

ADMIN_TRANSITIONS = {"APPROVED", "REJECTED"}


def is_platform_admin(user):
    return user.is_authenticated and (
        user.is_superuser or user.role == "ADMIN"
    )


@transaction.atomic
def transition_competition(competition, target_status, actor, review_note=""):
    competition = Competition.objects.select_for_update().get(
        pk=competition.pk
    )
    if target_status not in ALLOWED_TRANSITIONS.get(competition.status, set()):
        raise ValidationError(
            f"A competition cannot move from {competition.get_status_display()} "
            f"to {dict(Competition.STATUS_CHOICES).get(target_status, target_status)}."
        )
    if target_status in ADMIN_TRANSITIONS and not is_platform_admin(actor):
        raise ValidationError("Only an administrator can review submissions.")
    if target_status == "REJECTED" and not review_note.strip():
        raise ValidationError("A review note is required when requesting changes.")
    if target_status not in ADMIN_TRANSITIONS and is_platform_admin(actor):
        if target_status not in {"CANCELLED"}:
            raise ValidationError(
                "Administrators can only approve, reject, or cancel a competition."
            )

    competition.status = target_status
    if target_status in {"APPROVED", "REJECTED"}:
        competition.review_note = review_note.strip()
    elif target_status == "SUBMITTED":
        competition.review_note = ""
    elif target_status == "DRAFT":
        competition.review_note = ""
    if target_status == "RESULTS":
        has_results = CompetitionResult.objects.filter(
            participant__competition=competition,
        ).exclude(
            position__isnull=True,
            score__isnull=True,
            award="",
        ).exists()
        if not has_results:
            raise ValidationError(
                "Enter at least one participant result before publishing results."
            )
        CompetitionResult.objects.filter(
            participant__competition=competition
        ).update(published_at=timezone.now())
    competition.save(
        update_fields=("status", "review_note", "updated_at")
    )
    return competition

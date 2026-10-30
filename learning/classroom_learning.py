"""Read-only Learning views of sessions using existing classroom visibility."""

from django.db.models import Case, IntegerField, When

from .classroom_api_views import visible_classrooms
from .models import LiveSession


def visible_learning_sessions(user, course_id, *, lesson_id=None):
    if not getattr(user, "is_authenticated", False):
        return LiveSession.objects.none()
    sessions = LiveSession.objects.filter(
        classroom__in=visible_classrooms(user),
        classroom__course_id=course_id,
        classroom__is_active=True,
        status__in=[LiveSession.Status.SCHEDULED, LiveSession.Status.LIVE],
    )
    if lesson_id is not None:
        sessions = sessions.filter(lesson_id=lesson_id)
    return sessions.select_related(
        "classroom", "classroom__course", "lesson", "lesson__module",
    ).order_by(
        Case(When(status=LiveSession.Status.LIVE, then=0), default=1, output_field=IntegerField()),
        "scheduled_start", "pk",
    )

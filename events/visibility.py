from django.db.models import Case, CharField, F, Q, Value, When

from accounts.models import User
from organizations.permissions import OrganizationCapability, organizations_for_capability
from .models import Event, EventRegistration


def visible_events_for(user):
    """Drafts require current organization read capability, never a role label."""
    if user.is_authenticated and not User.objects.filter(pk=user.pk, is_active=True).exists():
        return Event.objects.none()
    scope = Q(status='PUBLISHED')
    if user.is_authenticated:
        scope |= Q(organizer__in=organizations_for_capability(user, OrganizationCapability.VIEW_EVENTS))
        # Keep a participant's closed/cancelled event history without exposing drafts.
        history = EventRegistration.objects.filter(talent__user_id=user.pk).values('event_id')
        scope |= Q(status__in=['CLOSED', 'CANCELLED'], pk__in=history)
    return Event.objects.filter(scope, Q(organizer__user__isnull=True) | Q(organizer__user__is_active=True),
                                organizer__status='ACTIVE').distinct()


def certificate_titles_for(certificates, user):
    return certificates.annotate(visible_event_title=Case(
        When(event__in=visible_events_for(user), then=F('event__title')),
        default=Value(''), output_field=CharField(),
    ))

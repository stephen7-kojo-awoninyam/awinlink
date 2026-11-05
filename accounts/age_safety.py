"""Server-authoritative minor privacy/contact rules. Roles never bypass these rules."""
import calendar
from itertools import combinations

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.utils import timezone

from .age_policy import GUARDIAN_CONSENT_VERSION, age_access_allowed
from .models import GuardianAuthorization, GuardianContactPermission, User


def cutoff(years):
    today = timezone.localdate()
    year = today.year - years
    return today.replace(year=year, day=min(today.day, calendar.monthrange(year, today.month)[1]))


def public_discovery_q(prefix="user__"):
    return Q(**{prefix + "date_of_birth__isnull": True}) | Q(**{prefix + "date_of_birth__lte": cutoff(18)})


def searchable_profiles(viewer, query):
    """Hidden location/name fields must not become a search-inference channel."""
    private_ids = []
    if getattr(viewer, "is_authenticated", False):
        private_ids = list(approved_authorizations().filter(guardian_id=viewer.pk).values_list("child_id", flat=True)) + [viewer.pk]
    return query.filter(public_discovery_q() | Q(user_id__in=private_ids))


def minor(user):
    return user.age_group in {"CHILD", "TEEN"}


def approved_authorizations():
    return GuardianAuthorization.objects.filter(status="APPROVED", guardian__is_active=True,
        guardian__date_of_birth__lte=cutoff(18), verified_by__isnull=False, verified_at__isnull=False,
        consent_version=GUARDIAN_CONSENT_VERSION, consented_at__isnull=False, revoked_at__isnull=True)


def guardian_of(viewer, child):
    return bool(minor(child) and getattr(viewer, "pk", None) and approved_authorizations().filter(
        guardian_id=viewer.pk, child_id=child.pk).exists())


def contact_allowed(first, second, *, calls=False):
    """Symmetric: every child's guardian must approve every counterpart in a group."""
    from connections.models import Connection
    if first.pk == second.pk:
        return True
    if not minor(first) and not minor(second):
        return True
    for person in (first, second):
        if not person.is_active or (minor(person) and not age_access_allowed(person)):
            return False
    for person, other in ((first, second), (second, first)):
        if person.age_group == "CHILD":
            authorization = approved_authorizations().filter(child=person).first()
            if not authorization:
                return False
            if authorization.guardian_id == other.pk:
                continue
            query = GuardianContactPermission.objects.filter(authorization=authorization, contact=other)
            if calls:
                query = query.filter(allow_calls=True)
            if not query.exists():
                return False
        elif person.age_group == "TEEN" and other.age_group not in {"CHILD", "TEEN"}:
            if guardian_of(other, person):
                continue
            inherited = GuardianContactPermission.objects.filter(authorization__in=approved_authorizations().filter(child=person), contact=other)
            if calls:
                inherited = inherited.filter(allow_calls=True)
            if inherited.exists():
                continue
            if not Connection.objects.filter(Q(sender=person, receiver=other) | Q(sender=other, receiver=person),
                                             status="ACCEPTED").exists():
                return False
    return True


def require_contact(user, others, *, calls=False):
    ids = set(others) | {user.pk}
    people = list(User.objects.filter(pk__in=ids))
    if len(people) != len(ids) or any(not contact_allowed(a, b, calls=calls) for a, b in combinations(people, 2)):
        raise PermissionDenied("This interaction requires age-safety approval.")


def group_allowed(ids, *, calls=False):
    people = list(User.objects.filter(pk__in=set(ids)))
    if not any(minor(person) for person in people):
        return True
    return all(contact_allowed(a, b, calls=calls) for a, b in combinations(people, 2))


def require_connection_request(sender, receiver):
    from .safety import blocked_user_ids
    if receiver.pk in blocked_user_ids(sender) or not sender.is_active or not receiver.is_active:
        raise PermissionDenied("This connection is unavailable.")
    # Teens may deliberately initiate a request to an adult. Messaging waits for acceptance.
    if sender.age_group == "TEEN" and receiver.age_group in {"ADULT", "UNKNOWN"}:
        return
    if not contact_allowed(sender, receiver):
        raise PermissionDenied("This connection requires age-safety approval.")


def visible_users_for(viewer):
    """Minors are excluded from public discovery, including legacy unknown-age viewers."""
    from connections.models import Connection
    adult_or_unknown = Q(date_of_birth__isnull=True) | Q(date_of_birth__lte=cutoff(18))
    allowed = set()
    child_allowed = set()
    if getattr(viewer, "is_authenticated", False) and User.objects.filter(pk=viewer.pk, is_active=True).exists():
        allowed.add(viewer.pk)
        allowed.update(approved_authorizations().filter(guardian_id=viewer.pk).values_list("child_id", flat=True))
        allowed.update(GuardianContactPermission.objects.filter(authorization__in=approved_authorizations(),
            contact_id=viewer.pk).values_list("authorization__child_id", flat=True))
        child_allowed = allowed.copy()
        pairs = Connection.objects.filter(Q(sender_id=viewer.pk) | Q(receiver_id=viewer.pk), status="ACCEPTED")
        for first, second in pairs.values_list("sender_id", "receiver_id"):
            allowed.add(second if first == viewer.pk else first)
    # Connections never override guardian approval for under-13s.
    teens = Q(date_of_birth__gt=cutoff(18), date_of_birth__lte=cutoff(13), pk__in=allowed)
    children = Q(pk__in=child_allowed) & (Q(guardian_authorization__in=approved_authorizations()) | Q(pk=getattr(viewer, "pk", None)))
    return User.objects.filter(is_active=True).filter(adult_or_unknown | teens | children).distinct()


def can_view_private_data(viewer, owner):
    return bool(getattr(viewer, "pk", None) == owner.pk or guardian_of(viewer, owner))


def public_user_data(data, owner, viewer=None):
    if minor(owner) and not can_view_private_data(viewer, owner):
        for key in ("email", "phone_number", "country", "city", "address", "date_of_birth", "first_name", "last_name"):
            if key in data:
                data[key] = ""
    return data

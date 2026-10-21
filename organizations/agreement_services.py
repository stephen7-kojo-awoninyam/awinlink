"""Consent-bound roster agreements. Locks: organizations by ID, agreement, roster."""
import hashlib
import json

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, OperationalError, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from .models import Organization, OrganizationTalent, TalentAgreement as Agreement, TalentAgreementConsent as Consent, TalentAgreementEvent as Event
from .permissions import OrganizationCapability as Cap, require_organization_capability
from .roster_services import require_unblocked_link, record as roster_event


class Conflict(APIException):
    status_code = 409
    default_detail = "This agreement or roster changed. Refresh and review it again."


def require_manager(actor, organization):
    require_organization_capability(actor, organization, Cap.MANAGE_AGREEMENTS)


def roster_snapshot(entry):
    return {"id": entry.pk, "organization_id": entry.organization_id, "talent_id": entry.talent_id,
            "name": entry.name, "tag": entry.tag, "roster": entry.roster, "talent_details": entry.talent_details}


TERM_FIELDS = ("kind", "title", "terms", "starts_on", "ends_on", "amount", "currency", "destination_id", "destination_tag", "destination_roster", "roster_snapshot")


def terms_snapshot(agreement):
    result = {key: getattr(agreement, key) for key in TERM_FIELDS}
    for key in ("starts_on", "ends_on"):
        result[key] = result[key].isoformat() if result[key] else None
    result["amount"] = f"{agreement.amount:.2f}" if agreement.amount is not None else None
    return result


def hash_terms(agreement):
    raw = json.dumps(terms_snapshot(agreement), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def event(agreement, actor, action, party="", reason="", snapshot=None):
    Event.objects.create(agreement=agreement, actor=actor, actor_name=actor.username, action=action,
        party=party, revision=agreement.revision, reason=reason,
        snapshot=snapshot if snapshot is not None else {"status": agreement.status, "terms_hash": agreement.terms_hash, "end_round": agreement.end_round})


def lock_organizations(ids):
    return {row.pk: row for row in Organization.objects.select_for_update().filter(pk__in=set(ids) - {None}).order_by("pk")}


def require_live_source(agreement, actor):
    entry = OrganizationTalent.objects.select_for_update(of=("self",)).select_related("talent__user").get(pk=agreement.roster_entry_id)
    if entry.status != "CONFIRMED" or not entry.talent_id or entry.talent_id != agreement.talent_id or roster_snapshot(entry) != agreement.roster_snapshot:
        raise Conflict("The original roster affiliation is no longer confirmed or has changed.")
    if not entry.talent.user.is_active or agreement.organization.status != "ACTIVE" or (agreement.destination_id and agreement.destination.status != "ACTIVE"):
        raise Conflict("All agreement participants must still be active.")
    require_unblocked_link(actor, agreement.organization, entry.talent)
    if agreement.destination_id:
        require_unblocked_link(actor, agreement.destination, entry.talent)
    return entry


@transaction.atomic
def create(actor, data):
    data = dict(data)
    entry_id = data.pop("roster_entry_id")
    organization_id = OrganizationTalent.objects.values_list("organization_id", flat=True).get(pk=entry_id)
    destination_id = data.pop("destination_id", None)
    organizations = lock_organizations([organization_id, destination_id])
    organization = organizations[organization_id]
    require_manager(actor, organization)
    entry = OrganizationTalent.objects.select_for_update().get(pk=entry_id)
    if entry.status != "CONFIRMED" or entry.talent_id is None:
        raise Conflict("Agreements require a claimed, confirmed roster affiliation.")
    if destination_id and destination_id not in organizations:
        raise ValidationError({"destination_id": "Choose an existing active destination organization."})
    agreement = Agreement(organization=organization, roster_entry=entry, talent_id=entry.talent_id,
        destination=organizations.get(destination_id), created_by=actor, roster_snapshot=roster_snapshot(entry), **data)
    require_live_source(agreement, actor)
    agreement.terms_hash = hash_terms(agreement)
    agreement.save()
    event(agreement, actor, "CREATED", "ORIGIN", snapshot=terms_snapshot(agreement))
    return agreement


def locked(agreement_id, actor):
    row = Agreement.objects.values("organization_id", "destination_id").get(pk=agreement_id)
    organizations = lock_organizations([row["organization_id"], row["destination_id"]])
    agreement = Agreement.objects.select_for_update(of=("self",)).select_related("talent__user").get(pk=agreement_id)
    agreement.organization = organizations[agreement.organization_id]
    if agreement.destination_id:
        agreement.destination = organizations[agreement.destination_id]
    # Keep account suspension and new block FK checks ordered against this
    # decision as well as organization/member changes. Lock every earlier
    # signer, since their authority is rechecked before final activation.
    user_ids = {actor.pk, agreement.talent.user_id, agreement.organization.user_id}
    if agreement.destination_id:
        user_ids.add(agreement.destination.user_id)
    user_ids.update(agreement.consents.values_list("actor_id", flat=True))
    try:
        # Block inserts can already hold foreign-key locks in a different
        # order. Fail closed instead of waiting into a cross-table deadlock.
        list(get_user_model().objects.select_for_update(nowait=True).filter(
            pk__in=user_ids - {None}).order_by("pk"))
    except OperationalError as exc:
        cause = exc.__cause__
        if getattr(cause, "sqlstate", None) == "55P03" or getattr(cause, "pgcode", None) == "55P03":
            raise Conflict("A participant account is being updated. Refresh and try again.") from exc
        raise
    return agreement


def require_revision(agreement, revision):
    if agreement.revision != revision:
        raise Conflict("The agreement revision changed. Review the new terms before consenting.")


@transaction.atomic
def revise(agreement_id, actor, revision, changes):
    agreement = locked(agreement_id, actor)
    require_manager(actor, agreement.organization)
    require_revision(agreement, revision)
    if agreement.status not in {"DRAFT", "PENDING"}:
        raise Conflict("Only draft or pending agreements may be revised.")
    allowed = {"title", "terms", "starts_on", "ends_on", "amount", "currency", "destination_tag", "destination_roster"}
    if not changes or not set(changes).issubset(allowed):
        raise ValidationError("Provide editable terms; agreement parties and source are immutable.")
    # Parties and the source affiliation cannot be silently replaced by editing.
    for key, value in changes.items():
        setattr(agreement, key, value)
    entry = OrganizationTalent.objects.select_for_update().get(pk=agreement.roster_entry_id)
    agreement.roster_snapshot = roster_snapshot(entry)
    require_live_source(agreement, actor)
    agreement.revision += 1
    agreement.status = "DRAFT"
    agreement.terms_hash = hash_terms(agreement)
    agreement.save()
    event(agreement, actor, "REVISED", "ORIGIN", snapshot=terms_snapshot(agreement))
    return agreement


def required_parties(agreement):
    return {"ORIGIN", "TALENT", "DESTINATION"} if agreement.kind == "TRANSFER" else {"ORIGIN", "TALENT"}


def require_party(agreement, actor, party):
    if not get_user_model().objects.filter(pk=actor.pk, is_active=True).exists():
        raise PermissionDenied("An active account is required.")
    if party == "TALENT" and agreement.talent.user_id == actor.pk:
        return
    if party == "ORIGIN":
        return require_manager(actor, agreement.organization)
    if party == "DESTINATION" and agreement.destination_id:
        return require_manager(actor, agreement.destination)
    raise PermissionDenied("You cannot act for this agreement party.")


def consent(agreement, actor, party, purpose):
    round_number = agreement.end_round if purpose == "END" else 0
    if Consent.objects.filter(agreement=agreement, revision=agreement.revision, party=party, purpose=purpose, round=round_number).exists():
        raise Conflict("This party already consented to this round.")
    Consent.objects.create(agreement=agreement, actor=actor, actor_name=actor.username, party=party,
        revision=agreement.revision, purpose=purpose, round=round_number, terms_hash=agreement.terms_hash)


def all_consented(agreement, purpose):
    rows = list(agreement.consents.select_related("actor").filter(revision=agreement.revision, purpose=purpose,
                round=agreement.end_round if purpose == "END" else 0))
    if {row.party for row in rows} != required_parties(agreement):
        return False
    # A suspended/revoked approver cannot leave usable pending authority behind.
    for row in rows:
        if row.actor is None or row.terms_hash != agreement.terms_hash:
            raise Conflict("An earlier consent is no longer usable. Revise and collect fresh consent.")
        try:
            require_party(agreement, row.actor, row.party)
        except PermissionDenied:
            raise Conflict("An earlier approver lost authority. Revise and collect fresh consent.") from None
        if purpose == "ACTIVATE":
            require_unblocked_link(row.actor, agreement.organization, agreement.talent)
            if agreement.destination_id:
                require_unblocked_link(row.actor, agreement.destination, agreement.talent)
    return True


def activate(agreement, actor):
    source = require_live_source(agreement, actor)
    if agreement.kind == "TRANSFER":
        source.status = "REMOVED"
        source.save(update_fields=["status", "updated_at"])
        destination = OrganizationTalent.objects.create(organization=agreement.destination, talent_id=agreement.talent_id,
            name=source.name, talent_details=source.talent_details, tag=agreement.destination_tag,
            roster=agreement.destination_roster, status="CONFIRMED")
        agreement.destination_entry = destination
        agreement.status = "COMPLETED"
        roster_event(source, actor, "TRANSFERRED_OUT", f"Agreement {agreement.pk}, revision {agreement.revision}")
        roster_event(destination, actor, "TRANSFERRED_IN", f"Agreement {agreement.pk}, revision {agreement.revision}")
    else:
        agreement.status = "ACTIVE"
    agreement.activated_at = timezone.now()
    event(agreement, actor, "TRANSFER_COMPLETED" if agreement.kind == "TRANSFER" else "ACTIVATED")


@transaction.atomic
def transition(agreement_id, actor, action, party, revision, consent_given=False, reason="", expected_end_round=None):
    agreement = locked(agreement_id, actor)
    require_revision(agreement, revision)
    require_party(agreement, actor, party)
    if action in {"REQUEST_END", "ACCEPT_END", "DECLINE_END"} and expected_end_round != agreement.end_round:
        raise Conflict("The ending request changed. Refresh before responding.")
    if action in {"SUBMIT", "ACCEPT", "REQUEST_END", "ACCEPT_END"} and consent_given is not True:
        raise ValidationError({"consent": "Explicit consent to these displayed terms is required."})
    if action in {"SUBMIT", "ACCEPT", "REQUEST_END", "ACCEPT_END"} and hash_terms(agreement) != agreement.terms_hash:
        raise Conflict("The stored terms no longer match their consent digest. Review and revise the agreement.")
    if action in {"DECLINE", "WITHDRAW", "REQUEST_END", "DECLINE_END"} and not reason.strip():
        raise ValidationError({"reason": "Provide a reason so all parties can understand the decision."})
    try:
        with transaction.atomic():
            if action == "SUBMIT" and party == "ORIGIN" and agreement.status == "DRAFT":
                require_live_source(agreement, actor)
                agreement.status = "PENDING"
                consent(agreement, actor, party, "ACTIVATE")
            elif action == "ACCEPT" and party != "ORIGIN" and agreement.status == "PENDING":
                require_live_source(agreement, actor)
                consent(agreement, actor, party, "ACTIVATE")
                if all_consented(agreement, "ACTIVATE"):
                    activate(agreement, actor)
            elif action == "DECLINE" and party != "ORIGIN" and agreement.status == "PENDING":
                agreement.status = "DECLINED"
            elif action == "WITHDRAW" and party == "ORIGIN" and agreement.status in {"DRAFT", "PENDING"}:
                agreement.status = "WITHDRAWN"
            elif action == "REQUEST_END" and agreement.status == "ACTIVE":
                agreement.status = "ENDING"
                agreement.end_round += 1
                consent(agreement, actor, party, "END")
            elif action == "ACCEPT_END" and agreement.status == "ENDING":
                consent(agreement, actor, party, "END")
                if all_consented(agreement, "END"):
                    agreement.status = "ENDED"
                    agreement.ended_at = timezone.now()
            elif action == "DECLINE_END" and agreement.status == "ENDING":
                if agreement.consents.filter(revision=agreement.revision, purpose="END", round=agreement.end_round, party=party).exists():
                    raise Conflict("The requesting party cannot decline its own ending request.")
                agreement.status = "ACTIVE"
            else:
                raise Conflict("This action is unavailable for this party or agreement state.")
            agreement.save()
            event(agreement, actor, action, party, reason)
    except IntegrityError:
        raise Conflict("A conflicting pending transfer or destination roster entry already exists. No roster changes were saved.") from None
    return agreement

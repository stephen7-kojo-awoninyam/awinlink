from django.contrib.auth.decorators import login_required
from django.db.models import Q, Exists, OuterRef
from django.shortcuts import get_object_or_404, render
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.exceptions import NotFound

from .models import Organization, OrganizationTalent, TalentAgreement as Agreement, TalentAgreementConsent
from .permissions import OrganizationCapability as Cap, organizations_for_capability
from .roster_views import RosterAPI
from . import agreement_services as services


def managed_ids(user):
    return set(organizations_for_capability(user, Cap.MANAGE_AGREEMENTS).values_list("pk", flat=True))


def accessible(user, ids):
    submitted = TalentAgreementConsent.objects.filter(agreement_id=OuterRef("pk"), purpose="ACTIVATE", party="ORIGIN", round=0)
    return Agreement.objects.select_related("organization", "destination", "talent__user", "roster_entry").annotate(
        any_submission=Exists(submitted)).filter(Q(organization_id__in=ids) |
        (Q(any_submission=True) & (Q(destination_id__in=ids) | Q(talent__user=user))))


class TermsInput(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    terms = serializers.CharField(max_length=20000)
    starts_on = serializers.DateField(allow_null=True, required=False, default=None)
    ends_on = serializers.DateField(allow_null=True, required=False, default=None)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0, allow_null=True, required=False, default=None)
    currency = serializers.RegexField(r"\A[A-Z]{3}\Z", required=False, default="GHS")
    destination_tag = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    destination_roster = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")

    def validate(self, data):
        current = self.context.get("agreement")
        def value(key):
            return data.get(key, getattr(current, key, None))
        if value("starts_on") and value("ends_on") and value("ends_on") < value("starts_on"):
            raise serializers.ValidationError({"ends_on": "End date must be on or after the start date."})
        kind = data.get("kind", getattr(current, "kind", None))
        if kind == "TRANSFER" and not value("destination_tag"):
            raise serializers.ValidationError({"destination_tag": "Name the destination affiliation tag."})
        if kind != "TRANSFER" and (value("destination_tag") or value("destination_roster")):
            raise serializers.ValidationError("Destination tag and roster apply only to transfers.")
        return data


class CreateInput(TermsInput):
    roster_entry_id = serializers.IntegerField(min_value=1, max_value=9223372036854775807)
    kind = serializers.ChoiceField(choices=Agreement.Kind.values)
    destination_id = serializers.IntegerField(min_value=1, max_value=9223372036854775807, required=False, allow_null=True, default=None)

    def validate(self, data):
        data = super().validate(data)
        if (data["kind"] == "TRANSFER") != bool(data.get("destination_id")):
            raise serializers.ValidationError({"destination_id": "Transfers need a destination; other agreements have no destination."})
        entry = get_object_or_404(OrganizationTalent.objects.filter(
            organization_id__in=managed_ids(self.context["request"].user)), pk=data["roster_entry_id"])
        if data.get("destination_id") == entry.organization_id:
            raise serializers.ValidationError({"destination_id": "Choose a different organization."})
        return data


class ExplicitConsent(serializers.BooleanField):
    def to_internal_value(self, value):
        if type(value) is not bool:
            self.fail("invalid", input=value)
        return value


class ActionInput(serializers.Serializer):
    action = serializers.ChoiceField(choices=["SUBMIT", "ACCEPT", "DECLINE", "WITHDRAW", "REQUEST_END", "ACCEPT_END", "DECLINE_END"])
    party = serializers.ChoiceField(choices=["ORIGIN", "DESTINATION", "TALENT"])
    expected_revision = serializers.IntegerField(min_value=1, max_value=2147483647)
    expected_end_round = serializers.IntegerField(min_value=0, max_value=2147483647, required=False)
    consent = ExplicitConsent(required=False, default=False)
    reason = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


def actions(row, user, ids, consents):
    parties = []
    if row.organization_id in ids:
        parties.append("ORIGIN")
    if row.destination_id in ids:
        parties.append("DESTINATION")
    if row.talent.user_id == user.pk:
        parties.append("TALENT")
    result = []
    for party in parties:
        accepted = any(c.party == party and c.revision == row.revision and c.purpose == "ACTIVATE" for c in consents)
        ending = any(c.party == party and c.revision == row.revision and c.purpose == "END" and c.round == row.end_round for c in consents)
        available = []
        if row.status == "DRAFT" and party == "ORIGIN":
            available = ["SUBMIT", "WITHDRAW"]
        elif row.status == "PENDING":
            available = ["WITHDRAW"] if party == "ORIGIN" else (["DECLINE"] if accepted else ["ACCEPT", "DECLINE"])
        elif row.status == "ACTIVE":
            available = ["REQUEST_END"]
        elif row.status == "ENDING" and not ending:
            available = ["ACCEPT_END", "DECLINE_END"]
        result.extend({"action": action, "party": party} for action in available)
    return result


def data(row, user, ids):
    result = {"id": row.pk, "roster_entry_id": row.roster_entry_id, "organization_id": row.organization_id,
        "organization_name": row.organization.name, "destination_name": row.destination.name if row.destination_id else None,
        "talent_name": row.talent.user.get_full_name() or row.talent.user.username,
        "status": row.status, "revision": row.revision, "end_round": row.end_round, "terms_hash": row.terms_hash,
        "destination_entry_id": row.destination_entry_id, "activated_at": row.activated_at, "ended_at": row.ended_at,
        **services.terms_snapshot(row)}
    consents = list(row.consents.all())
    submitted = [c for c in consents if c.party == "ORIGIN" and c.purpose == "ACTIVATE"]
    historical = row.organization_id not in ids and not any(c.revision == row.revision for c in submitted)
    if historical:
        # Keep previously shared consent evidence accessible without publishing
        # a later private draft or its withdrawal metadata.
        if not submitted:
            raise NotFound()
        published = max(submitted, key=lambda c: c.revision)
        snapshot = row.events.filter(revision=published.revision, action__in=["CREATED", "REVISED"]).values_list("snapshot", flat=True).last()
        if snapshot is None:
            raise NotFound()
        result.update(snapshot)
        result.update(revision=published.revision, status="SUPERSEDED", terms_hash=published.terms_hash, end_round=0)
        consents = [c for c in consents if c.revision <= published.revision]
    result["consents"] = [{"party": c.party, "purpose": c.purpose, "actor_name": c.actor_name, "revision": c.revision,
                           "round": c.round, "terms_hash": c.terms_hash, "created_at": c.created_at} for c in consents]
    result["actions"] = [] if historical else actions(row, user, ids, consents)
    result["ending_reason"] = row.events.filter(action="REQUEST_END", revision=row.revision).order_by("-pk").values_list("reason", flat=True).first() if row.status == "ENDING" else None
    result["can_revise"] = not historical and row.organization_id in ids and row.status in {"DRAFT", "PENDING"}
    return result


class Agreements(RosterAPI):
    def get(self, request):
        ids = managed_ids(request.user)
        rows = accessible(request.user, ids).prefetch_related("consents")
        if request.query_params.get("entry"):
            class Filter(serializers.Serializer):
                entry = serializers.IntegerField(min_value=1, max_value=9223372036854775807)
            f = Filter(data=request.query_params); f.is_valid(raise_exception=True)
            rows = rows.filter(roster_entry_id=f.validated_data["entry"])
        return self.page(request, rows, lambda row: data(row, request.user, ids))

    def post(self, request):
        serializer = CreateInput(data=request.data, context={"request": request}); serializer.is_valid(raise_exception=True)
        row = services.create(request.user, serializer.validated_data)
        return Response(data(row, request.user, managed_ids(request.user)), status=201, headers={"Cache-Control": "private, no-store"})


class AgreementDetail(RosterAPI):
    def row(self, request, pk):
        ids = managed_ids(request.user)
        return get_object_or_404(accessible(request.user, ids).prefetch_related("consents"), pk=pk), ids

    def get(self, request, pk):
        row, ids = self.row(request, pk)
        return Response(data(row, request.user, ids), headers={"Cache-Control": "private, no-store"})

    def patch(self, request, pk):
        row, _ = self.row(request, pk)
        class Revision(serializers.Serializer):
            expected_revision = serializers.IntegerField(min_value=1, max_value=2147483647)
        version = Revision(data=request.data); version.is_valid(raise_exception=True)
        serializer = TermsInput(data=request.data, partial=True, context={"agreement": row}); serializer.is_valid(raise_exception=True)
        row = services.revise(pk, request.user, version.validated_data["expected_revision"], serializer.validated_data)
        return Response(data(row, request.user, managed_ids(request.user)), headers={"Cache-Control": "private, no-store"})

    def post(self, request, pk):
        self.row(request, pk)
        serializer = ActionInput(data=request.data); serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        values["revision"] = values.pop("expected_revision"); values["consent_given"] = values.pop("consent")
        row = services.transition(pk, request.user, **values)
        return Response(data(row, request.user, managed_ids(request.user)), headers={"Cache-Control": "private, no-store"})


class AgreementHistory(AgreementDetail):
    def get(self, request, pk):
        row, ids = self.row(request, pk)
        events = row.events.all()
        if row.organization_id not in ids:
            published = row.consents.filter(party="ORIGIN", purpose="ACTIVATE").values_list("revision", flat=True)
            events = events.filter(revision__in=published)
        return self.page(request, events, lambda e: {"id": e.pk, "action": e.action, "party": e.party,
            "actor_name": e.actor_name, "revision": e.revision, "reason": e.reason, "snapshot": e.snapshot, "created_at": e.created_at})

    http_method_names = ["get", "head", "options"]


class RosterChoices(RosterAPI):
    def get(self, request):
        rows = OrganizationTalent.objects.select_related("organization").filter(organization_id__in=managed_ids(request.user),
            status="CONFIRMED", talent__user__is_active=True)
        return self.page(request, rows, lambda row: {"id": row.pk, "organization_id": row.organization_id,
            "organization_name": row.organization.name, "name": row.name, "tag": row.tag, "roster": row.roster})


class Destinations(RosterAPI):
    def get(self, request):
        return self.page(request, Organization.objects.filter(status="ACTIVE"), lambda org: {"id": org.pk, "name": org.name})


@login_required
def agreement_page(request):
    return render(request, "organizations/agreements.html")

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from rest_framework import serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .api_views import TeamAPIView
from .models import Organization, OrganizationTalent
from .permissions import OrganizationCapability as Cap, organizations_for_capability, require_organization_capability, has_organization_capability
from . import roster_services as services


class EntryInput(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    talent_details = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    tag = serializers.CharField(max_length=80)
    roster = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    username = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")


class ActionInput(serializers.Serializer):
    action = serializers.ChoiceField(choices=["LINK", "CONFIRM", "DECLINE", "REMOVE"])
    username = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


def entry_data(entry, user=None, manager=None):
    result = {key: getattr(entry, key) for key in ["id", "name", "talent_details", "tag", "roster", "status", "talent_id", "organization_id"]}
    result["organization_name"] = entry.organization.name
    if user is not None:
        recipient = entry.talent_id is not None and entry.talent.user_id == user.pk
        if manager is None:
            manager = has_organization_capability(user, entry.organization, Cap.MANAGE_RECRUITMENT)
        result["actions"] = (["CONFIRM", "DECLINE"] if recipient and entry.status == "PENDING" and entry.organization.status == "ACTIVE" else [])
        if manager and entry.status == "UNCLAIMED":
            result["actions"].append("LINK")
        if (recipient or manager) and entry.status != "REMOVED":
            result["actions"].append("REMOVE")
    return result


class RosterAPI(TeamAPIView):
    permission_classes = [IsAuthenticated]

    def page(self, request, rows, serialize):
        pager = PageNumberPagination()
        pager.page_size = 50
        response = pager.get_paginated_response([serialize(row) for row in pager.paginate_queryset(rows, request)])
        response["Cache-Control"] = "private, no-store"
        return response


class Workspaces(RosterAPI):
    def get(self, request):
        organizations = organizations_for_capability(request.user, Cap.VIEW_TALENTS)
        return self.page(request, organizations, lambda org: {"id": org.pk, "name": org.name,
            "can_manage": has_organization_capability(request.user, org, Cap.MANAGE_RECRUITMENT)})


class Roster(RosterAPI):
    def get(self, request, organization_id):
        organization = get_object_or_404(Organization, pk=organization_id)
        require_organization_capability(request.user, organization, Cap.VIEW_TALENTS)
        rows = organization.talent_roster.select_related("organization", "talent__user").all()
        manager = has_organization_capability(request.user, organization, Cap.MANAGE_RECRUITMENT)
        return self.page(request, rows, lambda row: entry_data(row, request.user, manager))

    def post(self, request, organization_id):
        get_object_or_404(Organization, pk=organization_id)
        serializer = EntryInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = services.create_entry(organization_id, request.user, dict(serializer.validated_data))
        return Response(entry_data(entry, request.user), status=201, headers={"Cache-Control": "no-store"})


class Mine(RosterAPI):
    def get(self, request):
        rows = OrganizationTalent.objects.select_related("organization", "talent__user").filter(talent__user=request.user)
        managers = {}
        def serialize(row):
            if row.organization_id not in managers:
                managers[row.organization_id] = has_organization_capability(request.user, row.organization, Cap.MANAGE_RECRUITMENT)
            return entry_data(row, request.user, managers[row.organization_id])
        return self.page(request, rows, serialize)


class Entry(RosterAPI):
    def visible_entry(self, request, pk):
        entry = get_object_or_404(OrganizationTalent.objects.select_related("organization", "talent__user"), pk=pk)
        if entry.talent_id is None or entry.talent.user_id != request.user.pk:
            require_organization_capability(request.user, entry.organization, Cap.VIEW_TALENTS)
        return entry

    def get(self, request, pk):
        entry = self.visible_entry(request, pk)
        return self.page(request, entry.history.all(), lambda event: {"id": event.pk, "action": event.action,
            "reason": event.reason, "created_at": event.created_at})

    def post(self, request, pk):
        self.visible_entry(request, pk)
        serializer = ActionInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = services.transition(pk, request.user, **serializer.validated_data)
        return Response(entry_data(entry, request.user), headers={"Cache-Control": "no-store"})


class Badges(RosterAPI):
    def get(self, request, talent_id=None, organization_id=None):
        rows = services.public_entries(request.user)
        if talent_id is not None:
            rows = rows.filter(talent_id=talent_id)
        if organization_id is not None:
            rows = rows.filter(organization_id=organization_id)
        return self.page(request, rows, lambda row: entry_data(row))


@login_required
def roster_page(request):
    return render(request, "organizations/roster.html")

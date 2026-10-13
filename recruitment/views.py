from organizations.permissions import (
    OrganizationCapability, require_request_organization, has_organization_capability,
)
from organizations.permissions import require_active_organization
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

from organizations.models import Organization
from .models import RecruitmentStage


# =========================================================
# RECRUITMENT PIPELINE
# =========================================================

@login_required
def recruitment_pipeline(request):

    organization = require_request_organization(request, OrganizationCapability.VIEW_RECRUITMENT)

    pipeline = RecruitmentStage.objects.filter(
        organization=organization
    ).select_related(
        "talent__user",
        "opportunity"
    ).order_by(
        "-created_at"
    )

    # -----------------------------------------
    # PIPELINE STAGES
    # -----------------------------------------

    shortlisted = pipeline.filter(
        stage="SHORTLISTED"
    )

    invited = pipeline.filter(
        stage="INVITED"
    )

    interview = pipeline.filter(
        stage="INTERVIEW"
    )

    selected = pipeline.filter(
        stage="SELECTED"
    )

    rejected = pipeline.filter(
        stage="REJECTED"
    )

    return render(
        request,
        "recruitment/pipeline.html",
        {
            "pipeline": pipeline,
            "shortlisted": shortlisted,
            "invited": invited,
            "interview": interview,
            "selected": selected,
            "rejected": rejected,
        }
    )


# =========================================================
# UPDATE RECRUITMENT STAGE
# =========================================================

@login_required
@require_POST
def update_pipeline_stage(
    request,
    stage_id,
    new_stage
):

    organization = require_request_organization(
        request, OrganizationCapability.MANAGE_RECRUITMENT,
        organization=get_object_or_404(RecruitmentStage, pk=stage_id).organization,
    )

    candidate = get_object_or_404(
        RecruitmentStage,
        id=stage_id,
        organization=organization
    )

    # -----------------------------------------
    # VALID STAGES
    # -----------------------------------------

    valid_stages = {
        "SHORTLISTED",
        "INVITED",
        "INTERVIEW",
        "SELECTED",
        "REJECTED",
    }

    # -----------------------------------------
    # PREVENT INVALID STAGE
    # -----------------------------------------

    if new_stage not in valid_stages:
        return redirect(
            "recruitment_pipeline"
        )

    # -----------------------------------------
    # UPDATE STAGE
    # -----------------------------------------

    candidate.stage = new_stage

    candidate.save(
        update_fields=["stage"]
    )

    return redirect(
        "recruitment_pipeline"
    )

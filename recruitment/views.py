from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required

from organizations.models import Organization
from .models import RecruitmentStage


# =========================================================
# RECRUITMENT PIPELINE
# =========================================================

@login_required
def recruitment_pipeline(request):

    organization = get_object_or_404(
        Organization,
        user=request.user
    )

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
def update_pipeline_stage(
    request,
    stage_id,
    new_stage
):

    organization = get_object_or_404(
        Organization,
        user=request.user
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
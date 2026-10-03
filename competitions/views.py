from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from talents.models import TalentProfile
from recommendations.services import RecommendationEngine

from .forms import (
    CompetitionForm,
    EvaluationForm,
    JudgeAssignmentForm,
    ResultForm,
    SubmissionForm,
)
from .models import (
    Competition,
    CompetitionEvaluation,
    CompetitionJudge,
    CompetitionParticipant,
    CompetitionResult,
)
from .permissions import (
    can_view_competition,
    get_managed_competition,
    get_owned_organization,
)
from .services import is_platform_admin, transition_competition


def competition_list(request):
    competitions = Competition.objects.filter(
        status__in=Competition.PUBLIC_STATUSES
    ).select_related("organization", "organization__category")
    query = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    if query:
        competitions = competitions.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(discipline__icontains=query)
            | Q(organization__name__icontains=query)
        )
    if category in dict(Competition.CATEGORIES):
        competitions = competitions.filter(category=category)
    recommendations = []
    if (
        request.user.is_authenticated
        and request.user.role == "ATHLETE"
    ):
        talent = TalentProfile.objects.filter(user=request.user).first()
        if talent:
            recommendations = (
                RecommendationEngine()
                .recommend_competitions_for_talent(talent, limit=3)
            )
    return render(
        request,
        "competitions/competition_list.html",
        {
            "competitions": competitions,
            "categories": Competition.CATEGORIES,
            "query": query,
            "selected_category": category,
            "competition_recommendations": recommendations,
        },
    )


def competition_detail(request, competition_id):
    competition = get_object_or_404(
        Competition.objects.select_related("organization", "organization__user"),
        pk=competition_id,
    )
    if not can_view_competition(request.user, competition):
        return render(request, "analytics/access_denied.html", status=403)
    participation = None
    if request.user.is_authenticated and request.user.role == "ATHLETE":
        talent = TalentProfile.objects.filter(user=request.user).first()
        if talent:
            participation = CompetitionParticipant.objects.filter(
                competition=competition,
                talent=talent,
            ).first()
    return render(
        request,
        "competitions/competition_detail.html",
        {
            "competition": competition,
            "participation": participation,
            "is_owner": (
                request.user.is_authenticated
                and competition.organization.user_id == request.user.pk
            ),
            "is_admin": is_platform_admin(request.user),
        },
    )


@login_required
def competition_create(request):
    organization = get_owned_organization(request.user)
    if organization is None:
        messages.error(request, "Only organizations can create competitions.")
        return redirect("competition_list")
    form = CompetitionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        competition = form.save(commit=False)
        competition.organization = organization
        competition.save()
        messages.success(request, "Competition draft created.")
        return redirect("competition_edit", competition_id=competition.pk)
    return render(
        request,
        "competitions/competition_create.html",
        {"form": form},
    )


@login_required
def competition_edit(request, competition_id):
    competition = get_managed_competition(request.user, competition_id)
    if competition is None:
        return render(request, "analytics/access_denied.html", status=403)
    if competition.status not in {"DRAFT", "REJECTED"}:
        messages.error(
            request,
            "Only draft competitions or competitions needing changes can be edited.",
        )
        return redirect("competition_dashboard")
    form = CompetitionForm(request.POST or None, instance=competition)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Competition details saved.")
        return redirect("competition_edit", competition_id=competition.pk)
    return render(
        request,
        "competitions/competition_edit.html",
        {"form": form, "competition": competition},
    )


@login_required
def competition_dashboard(request):
    organization = get_owned_organization(request.user)
    if organization is not None:
        competitions = Competition.objects.filter(organization=organization)
    elif is_platform_admin(request.user):
        competitions = Competition.objects.all()
    else:
        messages.error(
            request,
            "Competition management is available to organizations and admins.",
        )
        return redirect("competition_list")
    return render(
        request,
        "competitions/competition_dashboard.html",
        {"competitions": competitions},
    )


@login_required
def my_competitions(request):
    if request.user.role != "ATHLETE":
        messages.error(request, "Only talents can view their competitions.")
        return redirect("competition_list")
    talent = get_object_or_404(TalentProfile, user=request.user)
    participants = (
        CompetitionParticipant.objects.filter(talent=talent)
        .select_related("competition", "competition__organization")
        .order_by("-registered_at")
    )
    return render(
        request,
        "competitions/my_competitions.html",
        {"participants": participants},
    )


@login_required
def competition_register(request, competition_id):
    competition = get_object_or_404(Competition, pk=competition_id)
    if request.user.role != "ATHLETE":
        messages.error(request, "Only talents can register for competitions.")
        return redirect("competition_detail", competition_id=competition.pk)
    if request.method != "POST":
        return redirect("competition_detail", competition_id=competition.pk)
    talent = get_object_or_404(TalentProfile, user=request.user)
    try:
        with transaction.atomic():
            competition = Competition.objects.select_for_update().get(
                pk=competition.pk
            )
            if not competition.registration_open:
                raise ValidationError(
                    "Registration is closed, has not opened yet, or is full."
                )
            CompetitionParticipant.objects.create(
                competition=competition,
                talent=talent,
            )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    except IntegrityError:
        messages.info(request, "You are already registered for this competition.")
    else:
        messages.success(request, "You are registered for the competition.")
    return redirect("competition_detail", competition_id=competition.pk)


@login_required
def competition_submission(request, competition_id):
    competition = get_object_or_404(Competition, pk=competition_id)
    if request.user.role != "ATHLETE":
        return render(request, "analytics/access_denied.html", status=403)
    talent = get_object_or_404(TalentProfile, user=request.user)
    participant = get_object_or_404(
        CompetitionParticipant,
        competition=competition,
        talent=talent,
        status="REGISTERED",
    )
    if (
        competition.status != "ONGOING"
        or timezone.localdate() > competition.competition_end
    ):
        messages.error(request, "Submissions are not currently being accepted.")
        return redirect("competition_detail", competition_id=competition.pk)
    form = SubmissionForm(request.POST or None, instance=participant)
    if request.method == "POST" and form.is_valid():
        participant = form.save(commit=False)
        participant.submitted_at = timezone.now()
        participant.save(
            update_fields=("submission", "submission_url", "submitted_at")
        )
        messages.success(request, "Your submission has been saved.")
        return redirect("competition_detail", competition_id=competition.pk)
    return render(
        request,
        "competitions/registration.html",
        {"form": form, "competition": competition, "participant": participant},
    )


@login_required
@require_POST
def competition_action(request, competition_id):
    competition = get_managed_competition(request.user, competition_id)
    if competition is None:
        return render(request, "analytics/access_denied.html", status=403)
    action_statuses = {
        "submit": "SUBMITTED",
        "approve": "APPROVED",
        "reject": "REJECTED",
        "publish": "PUBLISHED",
        "close_registration": "REGISTRATION_CLOSED",
        "start": "ONGOING",
        "start_judging": "JUDGING",
        "publish_results": "RESULTS",
        "complete": "COMPLETED",
        "cancel": "CANCELLED",
        "return_to_draft": "DRAFT",
    }
    target_status = action_statuses.get(request.POST.get("action", ""))
    if target_status is None:
        messages.error(request, "Unknown competition action.")
        return redirect("competition_dashboard")
    owner = (
        request.user.is_authenticated
        and competition.organization.user_id == request.user.pk
    )
    if target_status in {"APPROVED", "REJECTED"}:
        if not is_platform_admin(request.user):
            return render(request, "analytics/access_denied.html", status=403)
    elif not owner and not (
        is_platform_admin(request.user) and target_status == "CANCELLED"
    ):
        return render(request, "analytics/access_denied.html", status=403)
    try:
        competition = transition_competition(
            competition,
            target_status,
            request.user,
            request.POST.get("review_note", ""),
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(
            request,
            f"Competition status changed to {competition.get_status_display()}.",
        )
    if (
        is_platform_admin(request.user)
        and request.POST.get("next") == "moderation"
    ):
        return redirect("competition_moderation")
    return redirect("competition_dashboard")


@login_required
def competition_moderation(request):
    if not is_platform_admin(request.user):
        return render(request, "analytics/access_denied.html", status=403)
    competitions = Competition.objects.filter(
        status="SUBMITTED"
    ).select_related("organization")
    return render(
        request,
        "competitions/moderation.html",
        {"competitions": competitions},
    )


@login_required
def competition_participants(request, competition_id):
    competition = get_object_or_404(
        Competition.objects.select_related("organization"),
        pk=competition_id,
    )
    if not can_view_competition(request.user, competition):
        return render(request, "analytics/access_denied.html", status=403)
    is_scout = request.user.role == "SCOUT"
    if is_scout and competition.status not in Competition.PUBLIC_STATUSES:
        return render(request, "analytics/access_denied.html", status=403)
    is_admin = is_platform_admin(request.user)
    is_owner = (
        request.user.is_authenticated
        and competition.organization.user_id == request.user.pk
    )
    judge_assignment = competition.judges.filter(
        coach=request.user,
    ).first() if request.user.is_authenticated else None
    if not (is_scout or is_admin or is_owner or judge_assignment):
        return render(request, "analytics/access_denied.html", status=403)
    participants = CompetitionParticipant.objects.filter(
        competition=competition,
        status="REGISTERED",
    ).select_related("talent", "talent__user")
    if is_scout:
        participants = participants.filter(talent__profile_visibility="PUBLIC")
    return render(
        request,
        "competitions/participants.html",
        {
            "competition": competition,
            "participants": participants,
            "is_scout": is_scout,
            "can_evaluate": (
                judge_assignment is not None
                and judge_assignment.role in {"JUDGE", "EVALUATOR"}
            ),
            "can_mentor": (
                judge_assignment is not None
                and judge_assignment.role == "MENTOR"
            ),
        },
    )


@login_required
def competition_assign_judge(request, competition_id):
    competition = get_managed_competition(request.user, competition_id)
    if competition is None or competition.organization.user_id != request.user.pk:
        return render(request, "analytics/access_denied.html", status=403)
    form = JudgeAssignmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        coach = form.cleaned_data["coach"]
        assignment, created = CompetitionJudge.objects.update_or_create(
            competition=competition,
            coach=coach,
            defaults={"role": form.cleaned_data["role"]},
        )
        messages.success(
            request,
            "Coach assigned to the competition."
            if created
            else "Coach assignment updated.",
        )
        return redirect("competition_assign_judge", competition_id=competition.pk)
    return render(
        request,
        "competitions/judging.html",
        {
            "competition": competition,
            "form": form,
            "assignments": competition.judges.select_related("coach"),
            "is_organizer": True,
        },
    )


@login_required
def my_judging(request):
    if request.user.role != "COACH":
        return render(request, "analytics/access_denied.html", status=403)
    assignments = CompetitionJudge.objects.filter(
        coach=request.user,
    ).select_related("competition", "competition__organization")
    return render(
        request,
        "competitions/judging.html",
        {"assignments": assignments, "is_judge_list": True},
    )


@login_required
def competition_evaluate(request, competition_id, participant_id):
    if request.user.role != "COACH":
        return render(request, "analytics/access_denied.html", status=403)
    competition = get_object_or_404(Competition, pk=competition_id)
    assignment = competition.judges.filter(coach=request.user).first()
    if assignment is None:
        return render(request, "analytics/access_denied.html", status=403)
    is_mentoring = assignment.role == "MENTOR"
    if not (
        (is_mentoring and competition.status == "ONGOING")
        or (not is_mentoring and competition.status == "JUDGING")
    ):
        messages.error(request, "Feedback is not currently being accepted.")
        return redirect("my_judging")
    participant = get_object_or_404(
        CompetitionParticipant,
        pk=participant_id,
        competition=competition,
        status="REGISTERED",
    )
    evaluation = CompetitionEvaluation.objects.filter(
        participant=participant,
        judge=request.user,
    ).first()
    if evaluation is None:
        evaluation = CompetitionEvaluation(
            participant=participant,
            judge=request.user,
            score=None,
        )
    form = EvaluationForm(
        request.POST or None,
        instance=evaluation,
        require_score=not is_mentoring,
    )
    if request.method == "POST" and form.is_valid():
        evaluation = form.save(commit=False)
        evaluation.participant = participant
        evaluation.judge = request.user
        evaluation.save()
        messages.success(request, "Evaluation saved.")
        return redirect(
            "competition_evaluate",
            competition_id=competition.pk,
            participant_id=participant.pk,
        )
    return render(
        request,
        "competitions/evaluation.html",
        {
            "form": form,
            "competition": competition,
            "participant": participant,
            "is_mentor": is_mentoring,
        },
    )


@login_required
def competition_results(request, competition_id):
    competition = get_object_or_404(
        Competition.objects.select_related("organization"),
        pk=competition_id,
    )
    if not can_view_competition(request.user, competition):
        return render(request, "analytics/access_denied.html", status=403)
    can_manage = (
        request.user.is_authenticated
        and competition.organization.user_id == request.user.pk
    )
    if (
        competition.status not in {"RESULTS", "COMPLETED"}
        and not can_manage
        and not is_platform_admin(request.user)
    ):
        return render(request, "analytics/access_denied.html", status=403)
    results = CompetitionResult.objects.filter(
        participant__competition=competition,
    ).select_related(
        "participant",
        "participant__talent",
        "participant__talent__user",
    )
    return render(
        request,
        "competitions/results.html",
        {
            "competition": competition,
            "results": results,
            "can_manage": can_manage,
            "participants": CompetitionParticipant.objects.filter(
                competition=competition,
                status="REGISTERED",
            ).select_related("talent", "talent__user"),
        },
    )


@login_required
@require_POST
def competition_save_result(request, competition_id, participant_id):
    competition = get_managed_competition(request.user, competition_id)
    if competition is None or competition.organization.user_id != request.user.pk:
        return render(request, "analytics/access_denied.html", status=403)
    if competition.status not in {"JUDGING", "RESULTS"}:
        messages.error(
            request,
            "Results can only be entered during judging or results.",
        )
        return redirect("competition_results", competition_id=competition.pk)
    participant = get_object_or_404(
        CompetitionParticipant,
        pk=participant_id,
        competition=competition,
        status="REGISTERED",
    )
    result, _ = CompetitionResult.objects.get_or_create(participant=participant)
    form = ResultForm(request.POST, instance=result)
    if form.is_valid():
        form.save()
        messages.success(request, "Competition result saved.")
    else:
        messages.error(request, "Please correct the result fields and try again.")
    return redirect("competition_results", competition_id=competition.pk)

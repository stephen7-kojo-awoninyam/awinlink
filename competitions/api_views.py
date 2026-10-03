from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from talents.models import TalentProfile
from recommendations.services import RecommendationEngine

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
from .serializers import (
    CompetitionEvaluationSerializer,
    CompetitionJudgeSerializer,
    CompetitionParticipantSerializer,
    PublicCompetitionParticipantSerializer,
    CompetitionResultSerializer,
    CompetitionSubmissionSerializer,
    CompetitionSerializer,
)
from .services import is_platform_admin, transition_competition

User = get_user_model()


class CompetitionListAPIView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        competitions = Competition.objects.filter(
            status__in=Competition.PUBLIC_STATUSES
        ).select_related("organization")
        category = request.query_params.get("category")
        search = request.query_params.get("search", "").strip()
        if isinstance(category, str) and category in dict(Competition.CATEGORIES):
            competitions = competitions.filter(category=category)
        if search:
            competitions = competitions.filter(
                Q(title__icontains=search)
                | Q(description__icontains=search)
                | Q(discipline__icontains=search)
                | Q(organization__name__icontains=search)
            )
        serializer = CompetitionSerializer(competitions.distinct(), many=True)
        return Response(serializer.data)


class CompetitionRecommendationsAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        if request.user.role != "ATHLETE":
            return Response(
                {"detail": "Only talents can receive competition recommendations."},
                status=status.HTTP_403_FORBIDDEN,
            )
        talent = TalentProfile.objects.filter(user=request.user).first()
        if talent is None:
            return Response(
                {"detail": "Complete your talent profile to get recommendations."},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            limit = int(request.query_params.get("limit", 10))
        except (TypeError, ValueError):
            return Response(
                {"detail": "Limit must be a number between 1 and 50."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not 1 <= limit <= 50:
            return Response(
                {"detail": "Limit must be a number between 1 and 50."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        recommendations = RecommendationEngine().recommend_competitions_for_talent(
            talent,
            limit=limit,
        )
        return Response(
            [
                {
                    "competition": CompetitionSerializer(
                        item["competition"]
                    ).data,
                    "score": item["score"],
                    "reasons": item["reasons"],
                }
                for item in recommendations
            ]
        )


class CompetitionCreateAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        organization = get_owned_organization(request.user)
        if organization is None:
            return Response(
                {"detail": "Only organizations can create competitions."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = CompetitionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        competition = serializer.save(organization=organization)
        return Response(
            CompetitionSerializer(competition).data,
            status=status.HTTP_201_CREATED,
        )


class CompetitionDetailAPIView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request, competition_id):
        competition = get_object_or_404(
            Competition.objects.select_related("organization"),
            pk=competition_id,
        )
        if not can_view_competition(request.user, competition):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(CompetitionSerializer(competition).data)

    def patch(self, request, competition_id):
        competition = get_managed_competition(request.user, competition_id)
        if competition is None or competition.organization.user_id != request.user.pk:
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
        if competition.status not in {"DRAFT", "REJECTED"}:
            return Response(
                {"detail": "Only draft competitions can be edited."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = CompetitionSerializer(
            competition,
            data=request.data,
            partial=True,
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data)


class CompetitionActionAPIView(APIView):
    permission_classes = (IsAuthenticated,)
    ACTIONS = {
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

    def post(self, request, competition_id):
        competition = get_managed_competition(request.user, competition_id)
        if competition is None:
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
        action = request.data.get("action", "")
        if not isinstance(action, str):
            return Response(
                {"action": ["Choose a valid competition action."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        target_status = self.ACTIONS.get(action)
        if target_status is None:
            return Response(
                {"action": ["Unknown competition action."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        owner = competition.organization.user_id == request.user.pk
        if target_status in {"APPROVED", "REJECTED"}:
            if not is_platform_admin(request.user):
                return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
        elif not owner and not (
            is_platform_admin(request.user) and target_status == "CANCELLED"
        ):
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
        review_note = request.data.get("review_note", "")
        if not isinstance(review_note, str):
            return Response(
                {"review_note": ["Enter a text review note."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            competition = transition_competition(
                competition,
                target_status,
                request.user,
                review_note,
            )
        except ValidationError as exc:
            return Response(
                {"detail": exc.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(CompetitionSerializer(competition).data)


class CompetitionRegisterAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, competition_id):
        if request.user.role != "ATHLETE":
            return Response(
                {"detail": "Only talents can register."},
                status=status.HTTP_403_FORBIDDEN,
            )
        competition = get_object_or_404(Competition, pk=competition_id)
        talent = get_object_or_404(TalentProfile, user=request.user)
        try:
            with transaction.atomic():
                competition = Competition.objects.select_for_update().get(
                    pk=competition.pk
                )
                if not competition.registration_open:
                    return Response(
                        {"detail": "Registration is closed or full."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                participant = CompetitionParticipant.objects.create(
                    competition=competition,
                    talent=talent,
                )
        except IntegrityError:
            return Response(
                {"detail": "Already registered."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(
            CompetitionParticipantSerializer(participant).data,
            status=status.HTTP_201_CREATED,
        )


class MyCompetitionRegistrationsAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        if request.user.role != "ATHLETE":
            return Response({"detail": "Only talents can view registrations."}, status=403)
        talent = get_object_or_404(TalentProfile, user=request.user)
        participants = CompetitionParticipant.objects.filter(
            talent=talent,
        ).select_related("competition", "competition__organization")
        serializer_class = (
            PublicCompetitionParticipantSerializer
            if request.user.role == "SCOUT"
            else CompetitionParticipantSerializer
        )
        return Response(serializer_class(participants, many=True).data)


class MyOrganizationCompetitionsAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        organization = get_owned_organization(request.user)
        if organization is None:
            return Response(
                {"detail": "Only organizations can view managed competitions."},
                status=status.HTTP_403_FORBIDDEN,
            )
        competitions = Competition.objects.filter(
            organization=organization,
        ).select_related("organization")
        return Response(CompetitionSerializer(competitions, many=True).data)


class CompetitionSubmissionAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    def patch(self, request, competition_id):
        if request.user.role != "ATHLETE":
            return Response({"detail": "Only talents can submit work."}, status=403)
        competition = get_object_or_404(Competition, pk=competition_id)
        if (
            competition.status != "ONGOING"
            or timezone.localdate() > competition.competition_end
        ):
            return Response(
                {"detail": "Submissions are not currently being accepted."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        talent = get_object_or_404(TalentProfile, user=request.user)
        participant = get_object_or_404(
            CompetitionParticipant,
            competition=competition,
            talent=talent,
            status="REGISTERED",
        )
        serializer = CompetitionSubmissionSerializer(
            data=request.data,
            partial=True,
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        participant.submission = serializer.validated_data.get(
            "submission",
            participant.submission,
        )
        participant.submission_url = serializer.validated_data.get(
            "submission_url",
            participant.submission_url,
        )
        participant.submitted_at = timezone.now()
        participant.save(
            update_fields=("submission", "submission_url", "submitted_at")
        )
        return Response(CompetitionParticipantSerializer(participant).data)


class CompetitionParticipantsAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, competition_id):
        competition = get_object_or_404(Competition, pk=competition_id)
        if not can_view_competition(request.user, competition):
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
        participants = CompetitionParticipant.objects.filter(
            competition=competition,
            status="REGISTERED",
        ).select_related("talent", "talent__user")
        if request.user.role == "SCOUT":
            if competition.status not in Competition.PUBLIC_STATUSES:
                return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
            participants = participants.filter(talent__profile_visibility="PUBLIC")
        elif not (
            is_platform_admin(request.user)
            or competition.organization.user_id == request.user.pk
            or competition.judges.filter(coach=request.user).exists()
        ):
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
        return Response(
            CompetitionParticipantSerializer(participants, many=True).data
        )


class CompetitionJudgeAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, competition_id):
        competition = get_object_or_404(Competition, pk=competition_id)
        if (
            not is_platform_admin(request.user)
            and competition.organization.user_id != request.user.pk
        ):
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
        assignments = CompetitionJudge.objects.filter(
            competition=competition
        ).select_related("coach")
        return Response(CompetitionJudgeSerializer(assignments, many=True).data)

    def post(self, request, competition_id):
        competition = get_object_or_404(Competition, pk=competition_id)
        if competition.organization.user_id != request.user.pk:
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
        coach_id = request.data.get("coach")
        try:
            coach_id = int(coach_id)
        except (TypeError, ValueError):
            return Response(
                {"coach": ["Select a valid coach account."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        coach = get_object_or_404(User, pk=coach_id, role="COACH")
        role = request.data.get("role", "JUDGE")
        valid_roles = dict(CompetitionJudge.ROLE_CHOICES)
        if not isinstance(role, str) or role not in valid_roles:
            return Response(
                {"role": ["Select a valid judge role."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        assignment, _ = CompetitionJudge.objects.update_or_create(
            competition=competition,
            coach=coach,
            defaults={"role": role},
        )
        return Response(
            CompetitionJudgeSerializer(assignment).data,
            status=status.HTTP_201_CREATED,
        )


class MyJudgingAssignmentsAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        if request.user.role != "COACH":
            return Response({"detail": "Only coaches can view assignments."}, status=403)
        assignments = CompetitionJudge.objects.filter(
            coach=request.user,
        ).select_related("competition", "competition__organization")
        return Response(CompetitionJudgeSerializer(assignments, many=True).data)


class CompetitionEvaluationAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    def put(self, request, competition_id, participant_id):
        if request.user.role != "COACH":
            return Response({"detail": "Only coaches can evaluate."}, status=403)
        competition = get_object_or_404(Competition, pk=competition_id)
        assignment = competition.judges.filter(coach=request.user).first()
        if assignment is None:
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
        is_mentoring = assignment.role == "MENTOR"
        if not (
            (is_mentoring and competition.status == "ONGOING")
            or (not is_mentoring and competition.status == "JUDGING")
        ):
            return Response(
                {"detail": "Feedback is not currently being accepted."},
                status=status.HTTP_400_BAD_REQUEST,
            )
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
        serializer = CompetitionEvaluationSerializer(
            evaluation,
            data=request.data,
            partial=evaluation is not None,
            context={"requires_score": not is_mentoring},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save(participant=participant, judge=request.user)
        return Response(serializer.data)


class CompetitionResultsAPIView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request, competition_id):
        competition = get_object_or_404(Competition, pk=competition_id)
        if not can_view_competition(request.user, competition):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if competition.status not in {"RESULTS", "COMPLETED"} and not (
            request.user.is_authenticated
            and (
                is_platform_admin(request.user)
                or competition.organization.user_id == request.user.pk
            )
        ):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        results = CompetitionResult.objects.filter(
            participant__competition=competition,
        ).select_related(
            "participant",
            "participant__talent",
            "participant__talent__user",
        )
        return Response(CompetitionResultSerializer(results, many=True).data)

    def put(self, request, competition_id, participant_id=None):
        if participant_id is None:
            return Response(
                {"detail": "Specify a participant result to update."},
                status=status.HTTP_405_METHOD_NOT_ALLOWED,
            )
        competition = get_managed_competition(request.user, competition_id)
        if competition is None or competition.organization.user_id != request.user.pk:
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
        if competition.status not in {"JUDGING", "RESULTS"}:
            return Response(
                {"detail": "Results can only be entered during judging or results."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        participant = get_object_or_404(
            CompetitionParticipant,
            pk=participant_id,
            competition=competition,
            status="REGISTERED",
        )
        result, _ = CompetitionResult.objects.get_or_create(participant=participant)
        serializer = CompetitionResultSerializer(
            result,
            data=request.data,
            partial=True,
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data)


class CompetitionModerationAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, competition_id=None):
        if not is_platform_admin(request.user):
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
        if competition_id is not None:
            competition = get_object_or_404(
                Competition,
                pk=competition_id,
                status="SUBMITTED",
            )
            return Response(CompetitionSerializer(competition).data)
        competitions = Competition.objects.filter(
            status="SUBMITTED"
        ).select_related("organization")
        return Response(CompetitionSerializer(competitions, many=True).data)

    def post(self, request, competition_id=None):
        if not is_platform_admin(request.user):
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
        if competition_id is None:
            return Response(
                {"detail": "Specify a competition to review."},
                status=status.HTTP_405_METHOD_NOT_ALLOWED,
            )
        competition = get_object_or_404(Competition, pk=competition_id)
        action = request.data.get("action", "")
        if not isinstance(action, str):
            return Response(
                {"action": ["Choose approve or reject."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        target = {"approve": "APPROVED", "reject": "REJECTED"}.get(action)
        if target is None:
            return Response(
                {"action": ["Choose approve or reject."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        review_note = request.data.get("review_note", "")
        if not isinstance(review_note, str):
            return Response(
                {"review_note": ["Enter a text review note."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            competition = transition_competition(
                competition,
                target,
                request.user,
                review_note,
            )
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CompetitionSerializer(competition).data)

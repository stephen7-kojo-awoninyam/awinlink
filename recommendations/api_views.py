from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from recommendations.api_serializers import (
    InterestPreferenceInputSerializer,
    RecommendationFeedbackBatchSerializer,
)
from recommendations.interest_learning import (
    InterestLearningService,
    interest_learning_enabled,
)
from recommendations.models import RecommendationFeedback
from recommendations.unified import unified_recommendations_enabled


def _rollout_state():
    return interest_learning_enabled() and unified_recommendations_enabled()


class RecommendationInterestPreferencesAPIView(APIView):
    """Read or change only the authenticated user's inference consent."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        preference = InterestLearningService.preference_for(request.user)
        return Response({
            "inferred_interests_enabled": bool(
                preference and preference.inferred_interests_enabled
            ),
            "rollout_enabled": _rollout_state(),
        })

    def patch(self, request):
        serializer = InterestPreferenceInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        preference = InterestLearningService.set_inferred_interests(
            request.user,
            serializer.validated_data["inferred_interests_enabled"],
        )
        return Response({
            "inferred_interests_enabled": preference.inferred_interests_enabled,
            "rollout_enabled": _rollout_state(),
        })


class InferredInterestsAPIView(APIView):
    """Expose a user's own coarse topics, never source activity records."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        preference = InterestLearningService.preference_for(request.user)
        enabled = bool(preference and preference.inferred_interests_enabled and _rollout_state())
        interests = InterestLearningService.inferred_interests(request.user) if enabled else []
        safe_interests = [
            {
                field: row[field]
                for field in ("topic", "strength", "signals", "explanation")
            }
            for row in interests
        ]
        return Response({"enabled": enabled, "interests": safe_interests})


class _RecommendationFeedbackAPIView(APIView):
    permission_classes = [IsAuthenticated]
    action = None

    def post(self, request):
        if not _rollout_state():
            return Response(
                {"detail": "Recommendation feedback is not enabled."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        serializer = RecommendationFeedbackBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entries = serializer.validated_data["entries"]
        accepted = InterestLearningService.record_feedback_bulk(
            request.user,
            [(entry["kind"], entry["item_id"]) for entry in entries],
            self.action,
        )
        if not accepted:
            return Response(
                {"detail": "One or more recommendation items are unavailable."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        unique_count = len({(entry["kind"], entry["item_id"]) for entry in entries})
        return Response({"recorded": unique_count}, status=status.HTTP_200_OK)


class RecommendationImpressionsAPIView(_RecommendationFeedbackAPIView):
    action = RecommendationFeedback.Action.IMPRESSION


class RecommendationDismissalsAPIView(_RecommendationFeedbackAPIView):
    action = RecommendationFeedback.Action.DISMISSED

    def delete(self, request, item_kind, item_id):
        if not _rollout_state():
            return Response(
                {"detail": "Recommendation feedback is not enabled."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        kind = str(item_kind).upper()
        if kind not in RecommendationFeedback.ItemKind.values or item_id <= 0:
            return Response(status=status.HTTP_404_NOT_FOUND)
        removed = InterestLearningService.remove_dismissal(request.user, kind, item_id)
        return Response(status=status.HTTP_204_NO_CONTENT if removed else status.HTTP_404_NOT_FOUND)

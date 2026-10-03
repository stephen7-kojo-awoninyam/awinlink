from django.urls import path

from .api_views import (
    CompetitionActionAPIView,
    CompetitionCreateAPIView,
    CompetitionDetailAPIView,
    CompetitionEvaluationAPIView,
    CompetitionJudgeAPIView,
    CompetitionListAPIView,
    CompetitionRecommendationsAPIView,
    CompetitionModerationAPIView,
    CompetitionParticipantsAPIView,
    CompetitionRegisterAPIView,
    CompetitionResultsAPIView,
    CompetitionSubmissionAPIView,
    MyOrganizationCompetitionsAPIView,
    MyCompetitionRegistrationsAPIView,
    MyJudgingAssignmentsAPIView,
)

app_name = "competitions_api"

urlpatterns = [
    path("", CompetitionListAPIView.as_view(), name="competition_list"),
    path(
        "recommended/",
        CompetitionRecommendationsAPIView.as_view(),
        name="competition_recommendations",
    ),
    path("create/", CompetitionCreateAPIView.as_view(), name="competition_create"),
    path("my/", MyCompetitionRegistrationsAPIView.as_view(), name="my_competitions"),
    path(
        "my/created/",
        MyOrganizationCompetitionsAPIView.as_view(),
        name="my_created_competitions",
    ),
    path("judging/", MyJudgingAssignmentsAPIView.as_view(), name="my_judging"),
    path("moderation/", CompetitionModerationAPIView.as_view(), name="moderation"),
    path(
        "moderation/<int:competition_id>/",
        CompetitionModerationAPIView.as_view(),
        name="moderation_review",
    ),
    path(
        "<int:competition_id>/",
        CompetitionDetailAPIView.as_view(),
        name="competition_detail",
    ),
    path(
        "<int:competition_id>/action/",
        CompetitionActionAPIView.as_view(),
        name="competition_action",
    ),
    path(
        "<int:competition_id>/register/",
        CompetitionRegisterAPIView.as_view(),
        name="competition_register",
    ),
    path(
        "<int:competition_id>/submission/",
        CompetitionSubmissionAPIView.as_view(),
        name="competition_submission",
    ),
    path(
        "<int:competition_id>/participants/",
        CompetitionParticipantsAPIView.as_view(),
        name="competition_participants",
    ),
    path(
        "<int:competition_id>/judges/",
        CompetitionJudgeAPIView.as_view(),
        name="competition_judges",
    ),
    path(
        "<int:competition_id>/participants/<int:participant_id>/evaluate/",
        CompetitionEvaluationAPIView.as_view(),
        name="competition_evaluation",
    ),
    path(
        "<int:competition_id>/results/",
        CompetitionResultsAPIView.as_view(),
        name="competition_results",
    ),
    path(
        "<int:competition_id>/results/<int:participant_id>/",
        CompetitionResultsAPIView.as_view(),
        name="competition_result",
    ),
]

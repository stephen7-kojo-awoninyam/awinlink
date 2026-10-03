from django.urls import path

from . import views


urlpatterns = [
    path("", views.competition_list, name="competition_list"),
    path("create/", views.competition_create, name="competition_create"),
    path("dashboard/", views.competition_dashboard, name="competition_dashboard"),
    path("my/", views.my_competitions, name="my_competitions"),
    path("moderation/", views.competition_moderation, name="competition_moderation"),
    path("<int:competition_id>/", views.competition_detail, name="competition_detail"),
    path(
        "<int:competition_id>/edit/",
        views.competition_edit,
        name="competition_edit",
    ),
    path(
        "<int:competition_id>/action/",
        views.competition_action,
        name="competition_action",
    ),
    path(
        "<int:competition_id>/register/",
        views.competition_register,
        name="competition_register",
    ),
    path(
        "<int:competition_id>/submission/",
        views.competition_submission,
        name="competition_submission",
    ),
    path(
        "<int:competition_id>/participants/",
        views.competition_participants,
        name="competition_participants",
    ),
    path(
        "<int:competition_id>/judges/",
        views.competition_assign_judge,
        name="competition_assign_judge",
    ),
    path("judging/", views.my_judging, name="my_judging"),
    path(
        "<int:competition_id>/participants/<int:participant_id>/evaluate/",
        views.competition_evaluate,
        name="competition_evaluate",
    ),
    path(
        "<int:competition_id>/results/",
        views.competition_results,
        name="competition_results",
    ),
    path(
        "<int:competition_id>/participants/<int:participant_id>/result/",
        views.competition_save_result,
        name="competition_save_result",
    ),
]

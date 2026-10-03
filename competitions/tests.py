from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from organizations.models import Organization
from talents.models import TalentProfile

from .models import (
    Competition,
    CompetitionEvaluation,
    CompetitionJudge,
    CompetitionParticipant,
    CompetitionResult,
)
from .services import transition_competition


class CompetitionWorkflowTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.organization_user = self.user_model.objects.create_user(
            username="competition_org",
            email="org@example.com",
            password="test-password",
            role="ORGANIZATION",
        )
        self.organization = Organization.objects.create(
            user=self.organization_user,
            name="North Star Academy",
            country="Ghana",
        )
        today = timezone.localdate()
        self.competition = Competition.objects.create(
            organization=self.organization,
            title="Youth Challenge",
            description="A challenge for emerging talent.",
            category="SPORTS",
            discipline="Football",
            status="PUBLISHED",
            registration_start=today - timedelta(days=1),
            registration_end=today + timedelta(days=7),
            competition_start=today + timedelta(days=8),
            competition_end=today + timedelta(days=10),
            max_participants=2,
        )
        self.api_client = APIClient()

    def create_user_and_talent(self, username, visibility="PUBLIC"):
        user = self.user_model.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="test-password",
            role="ATHLETE",
        )
        talent = TalentProfile.objects.create(
            user=user,
            profile_visibility=visibility,
        )
        return user, talent

    def test_only_organization_owner_can_create_and_edit_drafts(self):
        other_user = self.user_model.objects.create_user(
            username="other_org",
            email="other@example.com",
            password="test-password",
            role="ORGANIZATION",
        )
        self.client.force_login(other_user)
        response = self.client.get(
            reverse("competition_edit", args=(self.competition.pk,))
        )
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.organization_user)
        response = self.client.get(reverse("competition_create"))
        self.assertEqual(response.status_code, 200)

    def test_api_create_is_organization_only_and_drafts_are_not_public(self):
        data = {
            "title": "Robotics Sprint",
            "description": "Build a working prototype.",
            "category": "SCIENCE_TECHNOLOGY",
            "discipline": "Robotics",
            "registration_start": timezone.localdate().isoformat(),
            "registration_end": (timezone.localdate() + timedelta(days=5)).isoformat(),
            "competition_start": (timezone.localdate() + timedelta(days=6)).isoformat(),
            "competition_end": (timezone.localdate() + timedelta(days=8)).isoformat(),
        }
        talent_user, _ = self.create_user_and_talent("api_talent")
        self.api_client.force_authenticate(user=talent_user)
        response = self.api_client.post(
            reverse("competitions_api:competition_create"),
            data,
            format="json",
        )
        self.assertEqual(response.status_code, 403)

        self.api_client.force_authenticate(user=self.organization_user)
        response = self.api_client.post(
            reverse("competitions_api:competition_create"),
            data,
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        draft_id = response.data["id"]

        response = self.api_client.get(
            reverse("competitions_api:my_created_competitions")
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.data], [draft_id])

        self.api_client.force_authenticate(user=None)
        response = self.api_client.get(
            reverse(
                "competitions_api:competition_detail",
                args=(draft_id,),
            )
        )
        self.assertEqual(response.status_code, 404)
        response = self.api_client.get(
            reverse("competitions_api:competition_list")
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    @override_settings(
        STORAGES={
            "default": {
                "BACKEND": "django.core.files.storage.FileSystemStorage",
            },
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
            },
        }
    )
    def test_talent_can_get_personalized_competitions_from_web_and_api(self):
        talent_user, talent = self.create_user_and_talent("recommended_talent")
        talent.talent_category = "SPORTS"
        talent.talent_area = "Football"
        talent.save(update_fields=("talent_category", "talent_area"))
        self.api_client.force_authenticate(user=talent_user)

        response = self.api_client.get(
            reverse("competitions_api:competition_recommendations")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data[0]["competition"]["id"],
            self.competition.pk,
        )
        self.assertTrue(response.data[0]["reasons"])

        self.client.force_login(talent_user)
        response = self.client.get(reverse("competition_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Recommended for your talent")
        self.assertContains(response, "Personalized")

    def test_registration_is_role_limited_capacity_limited_and_unique(self):
        talent_user, talent = self.create_user_and_talent("talent_one")
        self.client.force_login(talent_user)
        register_url = reverse(
            "competition_register",
            args=(self.competition.pk,),
        )
        first_response = self.client.post(register_url)
        self.assertRedirects(
            first_response,
            reverse("competition_detail", args=(self.competition.pk,)),
        )
        self.assertTrue(
            CompetitionParticipant.objects.filter(
                competition=self.competition,
                talent=talent,
            ).exists()
        )

        self.client.post(register_url)
        self.assertEqual(
            CompetitionParticipant.objects.filter(
                competition=self.competition,
                talent=talent,
            ).count(),
            1,
        )

        _, second_talent = self.create_user_and_talent("talent_two")
        CompetitionParticipant.objects.create(
            competition=self.competition,
            talent=second_talent,
        )
        self.assertFalse(self.competition.registration_open)

    def test_submitted_competition_requires_admin_approval_before_publication(self):
        self.client.force_login(self.organization_user)
        data = {
            "title": "New Arts Challenge",
            "description": "Showcase new artistic work.",
            "category": "ARTS",
            "discipline": "Photography",
            "registration_start": timezone.localdate().isoformat(),
            "registration_end": (timezone.localdate() + timedelta(days=10)).isoformat(),
            "competition_start": (timezone.localdate() + timedelta(days=11)).isoformat(),
            "competition_end": (timezone.localdate() + timedelta(days=12)).isoformat(),
            "location": "Accra",
            "online": "",
            "requirements": "Submit original work.",
            "prizes": "Awards for finalists.",
            "rules": "One submission per participant.",
            "max_participants": "30",
        }
        response = self.client.post(reverse("competition_create"), data)
        self.assertEqual(response.status_code, 302)
        competition = Competition.objects.get(title="New Arts Challenge")
        self.assertEqual(competition.status, "DRAFT")

        self.client.post(
            reverse("competition_action", args=(competition.pk,)),
            {"action": "submit"},
        )
        competition.refresh_from_db()
        self.assertEqual(competition.status, "SUBMITTED")
        self.assertFalse(
            Competition.objects.filter(
                pk=competition.pk,
                status__in=Competition.PUBLIC_STATUSES,
            ).exists()
        )

        admin_user = self.user_model.objects.create_user(
            username="competition_admin",
            email="admin@example.com",
            password="test-password",
            role="ADMIN",
        )
        self.client.force_login(admin_user)
        response = self.client.get(reverse("competition_moderation"))
        self.assertContains(response, "New Arts Challenge")
        self.client.post(
            reverse("competition_action", args=(competition.pk,)),
            {"action": "approve"},
        )
        competition.refresh_from_db()
        self.assertEqual(competition.status, "APPROVED")

        self.client.force_login(self.organization_user)
        self.client.post(
            reverse("competition_action", args=(competition.pk,)),
            {"action": "publish"},
        )
        competition.refresh_from_db()
        self.assertEqual(competition.status, "PUBLISHED")

    def test_scout_only_sees_public_participants(self):
        _, public_talent = self.create_user_and_talent("public_talent")
        _, private_talent = self.create_user_and_talent(
            "private_talent",
            visibility="PRIVATE",
        )
        CompetitionParticipant.objects.create(
            competition=self.competition,
            talent=public_talent,
        )
        CompetitionParticipant.objects.create(
            competition=self.competition,
            talent=private_talent,
        )
        scout = self.user_model.objects.create_user(
            username="scout",
            email="scout@example.com",
            password="test-password",
            role="SCOUT",
        )
        self.client.force_login(scout)
        response = self.client.get(
            reverse("competition_participants", args=(self.competition.pk,))
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "public_talent")
        self.assertNotContains(response, "private_talent")

        self.api_client.force_authenticate(user=scout)
        response = self.api_client.get(
            reverse(
                "competitions_api:competition_participants",
                args=(self.competition.pk,),
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_assigned_coach_evaluates_and_organization_publishes_results(self):
        _, talent = self.create_user_and_talent("finalist")
        participant = CompetitionParticipant.objects.create(
            competition=self.competition,
            talent=talent,
            submission="Competition entry.",
        )
        coach = self.user_model.objects.create_user(
            username="judge_coach",
            email="judge@example.com",
            password="test-password",
            role="COACH",
        )
        CompetitionJudge.objects.create(
            competition=self.competition,
            coach=coach,
            role="JUDGE",
        )
        self.competition.status = "JUDGING"
        self.competition.save(update_fields=("status",))

        self.client.force_login(coach)
        response = self.client.post(
            reverse(
                "competition_evaluate",
                args=(self.competition.pk, participant.pk),
            ),
            {"score": "92.50", "feedback": "Excellent technique."},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            CompetitionEvaluation.objects.get(
                participant=participant,
                judge=coach,
            ).score,
            92.5,
        )

        self.client.force_login(self.organization_user)
        result_response = self.client.post(
            reverse(
                "competition_save_result",
                args=(self.competition.pk, participant.pk),
            ),
            {"position": "1", "score": "92.50", "award": "Winner"},
        )
        self.assertEqual(result_response.status_code, 302)
        transition_competition(
            self.competition,
            "RESULTS",
            self.organization_user,
        )
        result = CompetitionResult.objects.get(participant=participant)
        self.assertIsNotNone(result.published_at)
        self.assertEqual(result.award, "Winner")

    def test_assigned_mentor_can_leave_feedback_during_competition(self):
        _, talent = self.create_user_and_talent("mentee")
        participant = CompetitionParticipant.objects.create(
            competition=self.competition,
            talent=talent,
        )
        mentor = self.user_model.objects.create_user(
            username="assigned_mentor",
            email="mentor@example.com",
            password="test-password",
            role="COACH",
        )
        CompetitionJudge.objects.create(
            competition=self.competition,
            coach=mentor,
            role="MENTOR",
        )
        self.competition.status = "ONGOING"
        self.competition.save(update_fields=("status",))

        self.client.force_login(mentor)
        response = self.client.post(
            reverse(
                "competition_evaluate",
                args=(self.competition.pk, participant.pk),
            ),
            {"feedback": "Keep practising your footwork."},
        )

        self.assertEqual(response.status_code, 302)
        evaluation = CompetitionEvaluation.objects.get(
            participant=participant,
            judge=mentor,
        )
        self.assertIsNone(evaluation.score)
        self.assertEqual(evaluation.feedback, "Keep practising your footwork.")

    def test_rejection_requires_review_note_and_invalid_transition_fails(self):
        admin_user = self.user_model.objects.create_user(
            username="review_admin",
            email="review@example.com",
            password="test-password",
            role="ADMIN",
        )
        self.competition.status = "SUBMITTED"
        self.competition.save(update_fields=("status",))
        with self.assertRaises(ValidationError):
            transition_competition(
                self.competition,
                "REJECTED",
                admin_user,
            )
        transition_competition(
            self.competition,
            "REJECTED",
            admin_user,
            "Please include judging criteria.",
        )
        self.competition.refresh_from_db()
        self.assertEqual(self.competition.status, "REJECTED")
        self.assertEqual(
            self.competition.review_note,
            "Please include judging criteria.",
        )

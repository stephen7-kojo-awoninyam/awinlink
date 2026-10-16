from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.middleware.csrf import _get_new_csrf_string
from django.urls import resolve, reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from . import api_views, classroom_services as services
from .models import AdmissionState, AttendanceInterval, Classroom, ClassroomMembership, Course, Enrollment, Lesson, LiveSession, SessionAuditEvent
from .test_classroom_security import ClassroomFixture


class ClassroomAPITests(ClassroomFixture, APITestCase):
    def setUp(self):
        super().setUp()
        self.outsider = get_user_model().objects.create_user(username="api-outsider")
        self.root = "/api/learning/"
        self.rooms = self.root + "classrooms/"
        self.room = self.rooms + f"{self.classroom.pk}/"
        self.sessions = self.room + "sessions/"
        self.live = self.root + f"sessions/{self.session.pk}/"

    def auth(self, user):
        self.client.force_authenticate(user=user)

    def action(self, name, data=None, base=None):
        return self.client.post((base or self.live) + name + "/", data or {}, format="json")

    def request_via_api(self, user=None):
        self.auth(user or self.learner)
        response = self.action("request-admission")
        self.assertEqual(response.status_code, 200, response.data)
        return response.data["id"]

    def admit_via_api(self, user=None, moderator=None):
        participant_id = self.request_via_api(user)
        self.auth(moderator or self.host)
        response = self.action(f"participants/{participant_id}/admit")
        self.assertEqual(response.status_code, 200, response.data)
        return participant_id

    def schedule_payload(self):
        start = timezone.now() + timedelta(hours=1)
        return {"lesson": self.lesson.pk, "title": "API drawing", "scheduled_start": start.isoformat(),
                "scheduled_end": (start + timedelta(hours=1)).isoformat()}

    def assert_error(self, response, expected, code):
        self.assertEqual(response.status_code, expected, getattr(response, "data", None))
        self.assertEqual(response.data["error"]["code"], code)
        self.assertIn("detail", response.data["error"])

    def test_every_endpoint_requires_authentication(self):
        participant = self.request()
        reads = [self.rooms, self.room, self.sessions, self.live,
                 self.live + "participants/", self.live + "attendance/"]
        writes = [self.rooms, self.sessions] + [self.live + action + "/" for action in [
            "start", "request-admission", "join", "leave", "end", "cancel",
            f"participants/{participant.pk}/admit", f"participants/{participant.pk}/remove"]]
        for url in reads:
            with self.subTest(url=url):
                self.assert_error(self.client.get(url), 401, "not_authenticated")
        for url in writes:
            with self.subTest(url=url):
                self.assert_error(self.client.post(url, {}, format="json"), 401, "not_authenticated")

    def test_real_jwt_authentication_and_invalid_tokens(self):
        token = str(AccessToken.for_user(self.creator))
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(self.client.get(self.rooms).status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer invalid")
        self.assert_error(self.client.get(self.rooms), 401, "not_authenticated")
        token = AccessToken.for_user(self.creator)
        token.set_exp(lifetime=timedelta(seconds=-1))
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assert_error(self.client.get(self.rooms), 401, "not_authenticated")

    def test_session_authentication_requires_csrf_for_mutations(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.creator)
        self.assertEqual(client.get(self.rooms).status_code, 200)
        data = {"course": self.course.pk, "title": "Session authenticated room"}
        self.assert_error(client.post(self.rooms, data, format="json"), 403, "permission_denied")
        csrf = _get_new_csrf_string()
        client.cookies["csrftoken"] = csrf
        response = client.post(self.rooms, data, format="json", HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(response.status_code, 201, response.data)

    def test_inactive_accounts_cannot_read_or_write_using_stale_authentication(self):
        self.auth(self.creator)
        get_user_model().objects.filter(pk=self.creator.pk).update(is_active=False)
        self.assert_error(self.client.get(self.rooms), 403, "permission_denied")
        self.assert_error(self.action("end"), 403, "permission_denied")

    def test_create_uses_authenticated_creator_and_service(self):
        self.auth(self.creator)
        payload = {"course": self.course.pk, "title": "API classroom", "capacity": 8, "host": self.host.pk}
        with patch("learning.classroom_api_views.services.create_classroom", wraps=services.create_classroom) as create:
            response = self.client.post(self.rooms, payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(create.call_args.kwargs["actor"].pk, self.creator.pk)
        room = Classroom.objects.get(pk=response.data["id"])
        self.assertEqual(room.created_by_id, self.creator.pk)
        self.assertEqual(room.memberships.get(role="HOST").user_id, self.host.pk)
        self.assertTrue(room.audit_events.filter(event_type="CLASSROOM_CREATED").exists())

    def test_create_denies_other_users_and_account_role_shortcuts(self):
        for user in [self.host, self.cohost, self.learner, self.outsider, self.admin]:
            self.auth(user)
            self.assert_error(self.client.post(self.rooms, {"course": self.course.pk, "title": "Attack"}, format="json"),
                              403, "permission_denied")

    def test_input_rejects_role_identity_state_and_audit_injection(self):
        self.auth(self.creator)
        for key, value in {"actor": self.admin.pk, "created_by": self.admin.pk, "role": "HOST", "is_active": False,
                           "status": "LIVE", "metadata": {"approved": True}}.items():
            payload = {"course": self.course.pk, "title": "Injected", key: value}
            self.assert_error(self.client.post(self.rooms, payload, format="json"), 400, "invalid_request")
        participant = self.request_via_api()
        self.auth(self.host)
        self.assert_error(self.action(f"participants/{participant}/admit", {"admission_state": "ADMITTED"}), 400, "invalid_request")
        self.auth(self.learner)
        self.assert_error(self.action("request-admission", {"user": self.other.pk}), 400, "invalid_request")
        self.assertFalse(Classroom.objects.filter(title="Injected").exists())

    def test_list_and_detail_do_not_expose_other_classrooms(self):
        foreign = services.create_classroom(actor=self.outsider,
            course=Course.objects.create(creator=self.outsider, category=self.category,
                title="Private", slug="private", description="Secret"), title="Secret classroom")
        for user in [self.creator, self.host, self.cohost, self.learner]:
            self.auth(user)
            response = self.client.get(self.rooms)
            self.assertEqual(response.status_code, 200)
            self.assertIn(self.classroom.pk, [room["id"] for room in response.data["results"]])
            self.assertNotIn(foreign.pk, [room["id"] for room in response.data["results"]])
            self.assert_error(self.client.get(self.rooms + f"{foreign.pk}/"), 404, "not_found")
        for user in [self.outsider, self.admin]:
            self.auth(user)
            self.assert_error(self.client.get(self.room), 404, "not_found")
            self.assert_error(self.client.get(self.live), 404, "not_found")
            self.assert_error(self.client.get(self.live + "attendance/"), 404, "not_found")

    def test_unenrollment_inactive_membership_and_unapproved_course_revoke_discovery(self):
        self.auth(self.learner)
        Enrollment.objects.filter(user=self.learner).delete()
        self.assert_error(self.client.get(self.room), 404, "not_found")
        Enrollment.objects.create(user=self.learner, course=self.course)
        membership = ClassroomMembership.objects.create(classroom=self.classroom, user=self.learner, is_active=False)
        self.assert_error(self.client.get(self.room), 404, "not_found")
        membership.is_active = True
        membership.save()
        Course.objects.filter(pk=self.course.pk).update(status="DRAFT")
        self.assert_error(self.client.get(self.room), 404, "not_found")
        self.auth(self.creator)
        self.assertEqual(self.client.get(self.room).status_code, 200)

    def test_scheduling_is_host_scoped_and_validated(self):
        self.auth(self.host)
        response = self.client.post(self.sessions, self.schedule_payload(), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status"], "SCHEDULED")
        session_url = self.root + f"sessions/{response.data['id']}/"
        self.assertEqual(self.action("start", base=session_url).data["status"], "LIVE")
        for user in [self.cohost, self.learner]:
            self.auth(user)
            self.assert_error(self.client.post(self.sessions, self.schedule_payload(), format="json"), 403, "permission_denied")
        self.auth(self.host)
        payload = self.schedule_payload()
        payload["scheduled_end"] = payload["scheduled_start"]
        self.assert_error(self.client.post(self.sessions, payload, format="json"), 400, "invalid_request")
        payload = self.schedule_payload()
        payload["scheduled_start"] = "2026-12-01T12:00:00"
        self.assert_error(self.client.post(self.sessions, payload, format="json"), 400, "invalid_request")
        other_course = Course.objects.create(creator=self.creator, category=self.category,
            title="Other", slug="api-other", description="Other")
        payload = self.schedule_payload()
        payload["lesson"] = Lesson.objects.create(course=other_course, title="Other", order=1).pk
        self.assert_error(self.client.post(self.sessions, payload, format="json"), 404, "not_found")

    def test_lifecycle_management_denies_learners_and_cohosts(self):
        for user in [self.learner, self.cohost]:
            self.auth(user)
            for name in ["start", "end", "cancel"]:
                self.assert_error(self.action(name), 403, "permission_denied")
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "LIVE")

    def test_enrolled_learner_must_be_admitted_before_join(self):
        participant = self.request_via_api()
        self.assert_error(self.action("join", {"connection_id": str(uuid4())}), 403, "permission_denied")
        self.assert_error(self.action(f"participants/{participant}/admit"), 403, "permission_denied")
        self.auth(self.host)
        response = self.action(f"participants/{participant}/admit")
        self.assertEqual(response.data["admission_state"], "ADMITTED")
        self.auth(self.learner)
        response = self.action("join", {"connection_id": str(uuid4())})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(response.data["left_at"])
        self.assertTrue(self.session.audit_events.filter(event_type="JOINED").exists())

    def test_capacity_errors_preserve_waiting_participant(self):
        Classroom.objects.filter(pk=self.classroom.pk).update(capacity=3)
        participant = self.request_via_api()
        self.auth(self.host)
        self.assert_error(self.action(f"participants/{participant}/admit"), 400, "invalid_request")
        self.assertEqual(self.session.participants.get(pk=participant).admission_state, AdmissionState.WAITING)

    def test_cohost_may_moderate_learners_but_not_host(self):
        participant = self.admit_via_api(moderator=self.cohost)
        self.assertEqual(self.action(f"participants/{participant}/remove").status_code, 200)
        host = self.session.participants.get(membership__user=self.host)
        self.assert_error(self.action(f"participants/{host.pk}/remove"), 403, "permission_denied")

    def test_cross_session_participant_ids_do_not_modify_or_disclose_targets(self):
        other_session = self.schedule()
        target = services.request_admission(actor=self.learner, session=other_session)
        self.auth(self.host)
        for name in ["admit", "remove"]:
            self.assert_error(self.action(f"participants/{target.pk}/{name}"), 404, "not_found")
        target.refresh_from_db()
        self.assertEqual(target.admission_state, AdmissionState.WAITING)

    def test_reconnect_retries_and_stale_leaves_are_safe(self):
        self.admit_via_api()
        self.auth(self.learner)
        first_id, second_id = str(uuid4()), str(uuid4())
        first = self.action("join", {"connection_id": first_id})
        retry = self.action("join", {"connection_id": first_id})
        self.assertEqual(first.data["id"], retry.data["id"])
        second = self.action("join", {"connection_id": second_id})
        self.assertEqual(self.action("leave", {"connection_id": first_id}).status_code, 200)
        self.assertIsNone(AttendanceInterval.objects.get(pk=second.data["id"]).left_at)
        self.assert_error(self.action("join", {"connection_id": first_id}), 400, "invalid_request")
        self.assertEqual(self.action("leave", {"connection_id": second_id}).status_code, 200)
        self.assertEqual(self.action("leave", {"connection_id": second_id}).status_code, 200)
        self.assertEqual(self.session.audit_events.filter(event_type="JOINED").count(), 2)

    def test_other_users_cannot_leave_or_steal_connection(self):
        self.admit_via_api()
        self.admit_via_api(self.other)
        self.auth(self.learner)
        connection = str(uuid4())
        self.action("join", {"connection_id": connection})
        self.auth(self.other)
        self.assert_error(self.action("join", {"connection_id": connection}), 403, "permission_denied")
        self.assert_error(self.action("leave", {"connection_id": connection}), 403, "permission_denied")

    def test_leave_cleanup_survives_loss_of_enrollment_and_classroom_access(self):
        self.admit_via_api()
        self.auth(self.learner)
        connection = str(uuid4())
        self.action("join", {"connection_id": connection})
        Enrollment.objects.filter(user=self.learner).delete()
        Classroom.objects.filter(pk=self.classroom.pk).update(is_active=False)
        self.assert_error(self.client.get(self.room), 404, "not_found")
        self.assertEqual(self.action("leave", {"connection_id": connection}).status_code, 200)

    def test_roster_is_staff_only_and_session_details_show_only_own_participant(self):
        mine, theirs = self.request_via_api(), self.request_via_api(self.other)
        self.auth(self.learner)
        self.assert_error(self.client.get(self.live + "participants/"), 403, "permission_denied")
        response = self.client.get(self.live)
        self.assertEqual(response.data["my_participant"]["id"], mine)
        self.assertNotIn("participants", response.data)
        response = self.client.get(self.sessions)
        self.assertEqual(response.data["results"][0]["my_participant"]["id"], mine)
        self.auth(self.cohost)
        roster = self.client.get(self.live + "participants/")
        self.assertEqual(roster.status_code, 200, roster.data)
        self.assertTrue({mine, theirs}.issubset({row["id"] for row in roster.data["results"]}))
        self.assertTrue(all("email" not in row and "membership" not in row for row in roster.data["results"]))

    def test_attendance_is_scoped_and_connection_identifiers_are_private(self):
        self.admit_via_api()
        self.admit_via_api(self.other)
        for user in [self.learner, self.other, self.host]:
            self.auth(user)
            self.action("join", {"connection_id": str(uuid4())})
        self.auth(self.learner)
        response = self.client.get(self.live + f"attendance/?user={self.other.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("private", response["Cache-Control"])
        self.assertEqual([row["user"] for row in response.data["results"]], [self.learner.pk])
        self.assertTrue(all("connection_id" not in row for row in response.data["results"]))
        self.auth(self.cohost)
        response = self.client.get(self.live + "attendance/")
        self.assertEqual(response.data["count"], 3)
        self.assertTrue(all("connection_id" not in row for row in response.data["results"]))
        cohost = self.session.participants.get(membership__user=self.cohost)
        services.remove_participant(actor=self.host, session=self.session, participant=cohost)
        response = self.client.get(self.live + "attendance/")
        self.assertEqual(response.data["count"], 0)
        self.assert_error(self.client.get(self.live + "participants/"), 403, "permission_denied")

    def test_remove_closes_attendance_and_blocks_new_joins(self):
        participant = self.admit_via_api()
        self.auth(self.learner)
        connection = str(uuid4())
        self.action("join", {"connection_id": connection})
        self.auth(self.host)
        self.assertEqual(self.action(f"participants/{participant}/remove").status_code, 200)
        self.assertFalse(AttendanceInterval.objects.filter(participant_id=participant, left_at__isnull=True).exists())
        self.auth(self.learner)
        self.assert_error(self.action("join", {"connection_id": str(uuid4())}), 403, "permission_denied")
        self.assert_error(self.action("request-admission"), 403, "permission_denied")

    def test_end_cancel_and_terminal_state_errors(self):
        self.admit_via_api()
        self.auth(self.learner)
        self.action("join", {"connection_id": str(uuid4())})
        self.auth(self.host)
        ended = self.action("end")
        self.assertEqual(ended.data["status"], "ENDED")
        self.assertEqual(self.action("end").status_code, 200)
        self.assertFalse(AttendanceInterval.objects.filter(participant__session=self.session, left_at__isnull=True).exists())
        self.assert_error(self.action("start"), 400, "invalid_request")
        self.assert_error(self.action("join", {"connection_id": str(uuid4())}), 400, "invalid_request")
        scheduled = self.schedule()
        base = self.root + f"sessions/{scheduled.pk}/"
        self.assertEqual(self.action("cancel", base=base).data["status"], "CANCELLED")
        self.assertEqual(self.action("cancel", base=base).status_code, 200)
        self.assert_error(self.action("start", base=base), 400, "invalid_request")

    def test_malformed_payloads_and_missing_objects_have_consistent_errors(self):
        self.auth(self.creator)
        for payload in [[], {"course": "bad", "title": "Art"}, {"course": self.course.pk, "title": " "},
                        {"course": self.course.pk, "title": "Art", "capacity": 0}]:
            self.assert_error(self.client.post(self.rooms, payload, format="json"), 400, "invalid_request")
        self.assert_error(self.client.post(self.rooms, "{", content_type="application/json"), 400, "invalid_request")
        self.assert_error(self.client.post(self.rooms, "title=x", content_type="application/x-www-form-urlencoded"),
                          415, "unsupported_media_type")
        self.assert_error(self.client.get(self.rooms + "999999/"), 404, "not_found")
        self.assert_error(self.client.post(self.rooms, {"course": 999999, "title": "Missing"}, format="json"), 404, "not_found")
        self.assert_error(self.client.get(self.rooms + "?course=invalid"), 400, "invalid_request")
        self.assert_error(self.action("join", {"connection_id": "bad"}), 400, "invalid_request")

    def test_get_and_generic_writes_never_trigger_mutations(self):
        self.auth(self.host)
        audits = SessionAuditEvent.objects.count()
        for action in ["start", "join", "leave", "end", "cancel", "request-admission"]:
            self.assert_error(self.client.get(self.live + action + "/"), 405, "method_not_allowed")
        self.assert_error(self.client.patch(self.room, {"capacity": 100}, format="json"), 405, "method_not_allowed")
        self.assert_error(self.client.delete(self.live), 405, "method_not_allowed")
        self.assertEqual(SessionAuditEvent.objects.count(), audits)

    def test_safe_conflict_and_unexpected_error_responses_roll_back_changes(self):
        participant = self.request_via_api()
        self.auth(self.host)
        with patch("learning.classroom_services._audit", side_effect=IntegrityError("private SQL")):
            response = self.action(f"participants/{participant}/admit")
        self.assert_error(response, 409, "conflict")
        self.assertNotIn("private SQL", str(response.data))
        self.assertEqual(self.session.participants.get(pk=participant).admission_state, "WAITING")
        with patch("learning.classroom_services._audit", side_effect=RuntimeError("private server data")), self.assertLogs("learning.classroom_api_views", level="ERROR"):
            response = self.action(f"participants/{participant}/admit")
        self.assert_error(response, 500, "server_error")
        self.assertNotIn("private server data", str(response.data))
        self.assertEqual(self.session.participants.get(pk=participant).admission_state, "WAITING")

    def test_pagination_and_course_filter_preserve_visibility(self):
        self.auth(self.creator)
        services.create_classroom(actor=self.creator, course=self.course, title="Second")
        response = self.client.get(self.rooms + f"?course={self.course.pk}&page_size=1")
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertIsNotNone(response.data["next"])
        self.assert_error(self.client.get(self.rooms + "?page=999999"), 404, "not_found")

    def test_existing_learning_routes_still_resolve_and_respond(self):
        self.auth(self.learner)
        for url, view in [
            (self.root + "categories/", api_views.LearningCategoryListAPIView),
            (self.root + "courses/", api_views.CourseListAPIView),
            (self.root + f"courses/{self.course.pk}/", api_views.CourseDetailAPIView),
            (self.root + f"courses/{self.course.pk}/lessons/", api_views.CourseLessonsAPIView),
            (self.root + "my-enrollments/", api_views.MyEnrollmentsAPIView),
        ]:
            self.assertIs(resolve(url).func.view_class, view)
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertEqual(reverse("classroom_session_start", kwargs={"session_id": self.session.pk}), self.live + "start/")

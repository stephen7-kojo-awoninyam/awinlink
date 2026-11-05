from datetime import date, timedelta
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.test import TestCase, TransactionTestCase, SimpleTestCase, override_settings
from django.utils import timezone
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from accounts.age_policy import GUARDIAN_CONSENT_VERSION, approve_guardian, revoke_guardian
from accounts.age_safety import contact_allowed, visible_users_for
from accounts.guardian_permissions import change_permission
from accounts.models import GuardianAuthorization, GuardianContactPermission, GuardianCoursePermission, User
from connections.models import Connection
from learning.age_permissions import course_allowed
from learning import classroom_services as rooms, whiteboard_services as board
from learning.models import Course, LearningCategory, Lesson, Enrollment, AttendanceInterval
from messaging.models import Conversation, ConversationParticipant, Message, Call, CallParticipant
from messaging.realtime import can_access
from talents.models import TalentProfile


class AgeFeatureFixture:
    def setUp(self):
        super().setUp()
        cache.clear()
        self.adult = User.objects.create_user("adult", date_of_birth=date(1980, 1, 1), role="COACH")
        self.guardian = User.objects.create_user("guardian", date_of_birth=date(1980, 1, 1))
        self.reviewer = User.objects.create_user("reviewer", is_staff=True)
        self.child = User.objects.create_user("child", date_of_birth=date(2020, 1, 1), is_active=False,
                                              email="minor-private@example.invalid", country="GH", phone_number="private-phone", last_name="PrivateSurname")
        self.teen = User.objects.create_user("teen", date_of_birth=date(2010, 1, 1))
        self.unknown = User.objects.create_user("legacy", role="ADMIN")
        self.authorization = GuardianAuthorization.objects.create(child=self.child, guardian=self.guardian,
            nominated_email="guardian@example.invalid", verified_by=self.reviewer, verified_at=timezone.now())
        approve_guardian(actor=self.guardian, authorization_id=self.authorization.pk,
                         accepted=True, version=GUARDIAN_CONSENT_VERSION)
        self.child.refresh_from_db()
        self.profile = TalentProfile.objects.create(user=self.child, city="PrivateCity", country="GH", biography="PrivateBio")
        self.category = LearningCategory.objects.create(name="Safety learning")
        self.course = Course.objects.create(creator=self.adult, title="Safe course", slug="safe-course",
                                           category=self.category, status="APPROVED", is_free=True)
        self.lesson = Lesson.objects.create(course=self.course, title="Lesson", order=1)

    def grant_contact(self, calls=False, contact=None):
        return change_permission(actor=self.guardian, authorization_id=self.authorization.pk, action="allow_contact",
                                 data={"username": (contact or self.adult).username, "allow_calls": calls})

    def grant_course(self, live=False):
        return change_permission(actor=self.guardian, authorization_id=self.authorization.pk, action="allow_course",
                                 data={"course_id": self.course.pk, "allow_live": live})

    def historical_room(self, *people):
        room = Conversation.objects.create(created_by=self.adult)
        ConversationParticipant.objects.bulk_create([ConversationParticipant(conversation=room, user=person) for person in people])
        Message.objects.bulk_create([Message(conversation=room, sender=self.adult, content="private-history", message_type="TEXT")])
        return room

    def api(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def live_class(self):
        self.grant_course(live=True)
        Enrollment.objects.create(user=self.child, course=self.course)
        room = rooms.create_classroom(actor=self.adult, course=self.course, title="Room")
        now = timezone.now()
        session = rooms.schedule_session(actor=self.adult, classroom=room, lesson=self.lesson, title="Live",
            scheduled_start=now + timedelta(minutes=1), scheduled_end=now + timedelta(hours=1))
        participant = rooms.request_admission(actor=self.child, session=session)
        rooms.admit_participant(actor=self.adult, session=session, participant=participant)
        rooms.start_session(actor=self.adult, session=session)
        return room, session, participant


class AgeFeatureSecurityTests(AgeFeatureFixture, TestCase):
    def test_minor_discovery_is_private_to_guardian_and_approved_contacts(self):
        for viewer in (AnonymousUser(), self.adult, self.unknown, self.teen):
            self.assertFalse(visible_users_for(viewer).filter(pk=self.child.pk).exists())
        self.assertTrue(visible_users_for(self.guardian).filter(pk=self.child.pk).exists())
        self.grant_contact()
        self.assertTrue(visible_users_for(self.adult).filter(pk=self.child.pk).exists())
        response = self.api(self.adult).get(f"/api/talents/{self.profile.pk}/")
        self.assertEqual(response.status_code, 200, response.data)
        for value in ("PrivateCity", "PrivateBio", "PrivateSurname", "private-phone", "minor-private@example.invalid"):
            self.assertNotIn(value, str(response.data))
        self.assertEqual(response.data["city"], "")
        self.assertTrue(response.data["interaction_capabilities"]["can_message"])
        self.assertFalse(response.data["interaction_capabilities"]["can_call"])
        self.client.force_login(self.adult)
        response = self.client.get(reverse("talent_profile", args=[self.profile.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "PrivateCity")
        self.assertNotContains(response, "PrivateBio")

    def test_guardian_and_owner_retain_private_profile_data(self):
        for viewer in (self.guardian, self.child):
            result = self.api(viewer).get(f"/api/talents/{self.profile.pk}/")
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.data["city"], "PrivateCity")

    def test_existing_connections_never_override_under13_guardian_approval(self):
        Connection.objects.bulk_create([Connection(sender=self.child, receiver=self.adult, status="ACCEPTED")])
        self.assertFalse(contact_allowed(self.adult, self.child))
        self.assertFalse(visible_users_for(self.adult).filter(pk=self.child.pk).exists())

    def test_unsolicited_private_contact_is_denied_for_all_roles_and_unknown_accounts(self):
        for role in ("ATHLETE", "SCOUT", "COACH", "ORGANIZATION", "ADMIN"):
            User.objects.filter(pk=self.adult.pk).update(role=role)
            response = self.api(self.adult).post("/api/messaging/conversations/create/", {"user_ids": [self.child.pk]}, format="json")
            self.assertEqual(response.status_code, 403, response.data)
        self.assertEqual(self.api(self.unknown).post("/api/messaging/conversations/create/", {"user_ids": [self.child.pk]}, format="json").status_code, 403)
        self.assertFalse(Conversation.objects.exists())

    def test_old_room_history_send_and_read_are_denied_before_approval(self):
        room = self.historical_room(self.adult, self.child)
        client = self.api(self.adult)
        for path in (f"/api/messaging/conversations/{room.pk}/", f"/api/messaging/conversations/{room.pk}/messages/"):
            response = client.get(path)
            self.assertEqual(response.status_code, 403, response.data)
            self.assertNotIn("private-history", str(response.data))
        self.assertFalse(can_access(self.adult, room.pk))
        response = client.post(f"/api/messaging/conversations/{room.pk}/messages/create/", {"content": "bypass", "message_type": "TEXT"})
        self.assertEqual(response.status_code, 403)
        self.grant_contact()
        self.assertTrue(can_access(self.adult, room.pk))
        self.assertEqual(client.get(f"/api/messaging/conversations/{room.pk}/messages/").status_code, 200)

    def test_calls_require_separate_approval_and_guest_cannot_bypass_it(self):
        self.grant_contact()
        room = self.historical_room(self.adult, self.child)
        endpoint = f"/api/messaging/conversations/{room.pk}/calls/start/"
        self.assertEqual(self.api(self.adult).post(endpoint, {"call_type": "VOICE"}).status_code, 403)
        self.grant_contact(calls=True)
        result = self.api(self.adult).post(endpoint, {"call_type": "VOICE"})
        self.assertEqual(result.status_code, 201, result.data)
        call = Call.objects.get(pk=result.data["id"])
        guest = User.objects.create_user("unapproved-guest", date_of_birth=date(1980, 1, 1))
        result = self.api(self.adult).post(f"/api/messaging/calls/{call.pk}/invite/", {"username": guest.username})
        self.assertEqual(result.status_code, 403, result.data)
        change_permission(actor=self.guardian, authorization_id=self.authorization.pk, action="remove_contact", data={"username": self.adult.username})
        call.refresh_from_db()
        self.assertEqual(call.status, "ENDED")
        self.assertFalse(can_access(self.adult, room.pk))

    def test_group_membership_checks_every_counterpart(self):
        self.grant_contact()
        other = User.objects.create_user("unapproved-peer")
        room = self.historical_room(self.adult, self.child)
        with self.assertRaises(PermissionDenied):
            ConversationParticipant.objects.create(conversation=room, user=other)
        room = self.historical_room(self.adult, self.child, other)
        self.assertFalse(can_access(self.adult, room.pk))

    def test_teens_can_initiate_connections_but_unknown_and_adult_unsolicited_contact_is_denied(self):
        self.assertFalse(contact_allowed(self.adult, self.teen))
        self.assertFalse(contact_allowed(self.unknown, self.teen))
        connection = Connection.objects.create(sender=self.teen, receiver=self.adult)
        self.assertFalse(contact_allowed(self.adult, self.teen))
        from connections.services import respond_to_connection
        respond_to_connection(connection.pk, self.adult, "ACCEPTED")
        self.assertTrue(contact_allowed(self.adult, self.teen))

    def test_course_permission_does_not_grant_private_contact_or_live_access(self):
        self.assertFalse(course_allowed(self.child, self.course))
        self.grant_course()
        self.assertTrue(course_allowed(self.child, self.course))
        self.assertFalse(course_allowed(self.child, self.course, live=True))
        self.assertFalse(contact_allowed(self.adult, self.child))
        from learning.services import LearningService
        LearningService.enroll(self.course, self.child)
        self.assertEqual(self.api(self.child).get(f"/api/learning/lessons/{self.lesson.pk}/").status_code, 200)

    def test_guardian_scope_and_strict_booleans_cannot_be_forged(self):
        endpoint = f"/api/auth/guardians/{self.authorization.pk}/"
        body = {"action": "allow_contact", "username": self.adult.username, "allow_calls": True}
        self.assertEqual(self.api(self.adult).post(endpoint, body, format="json").status_code, 404)
        self.assertEqual(self.api(self.child).post(endpoint, body, format="json").status_code, 404)
        self.assertEqual(self.api(self.guardian).post(endpoint, {**body, "allow_calls": "true"}, format="json").status_code, 400)
        self.assertFalse(GuardianContactPermission.objects.exists())
        self.assertFalse(self.guardian.is_staff)

    def test_guardian_course_revocation_closes_attendance_and_board_and_retains_progress(self):
        room, session, participant = self.live_class()
        connection_id = uuid4()
        rooms.join_session(actor=self.child, session=session, connection_id=connection_id)
        board.snapshot(actor=self.child, session_id=session.pk)
        change_permission(actor=self.guardian, authorization_id=self.authorization.pk, action="remove_course", data={"course_id": self.course.pk})
        participant.refresh_from_db()
        self.assertEqual(participant.admission_state, "REMOVED")
        self.assertFalse(AttendanceInterval.objects.filter(participant=participant, left_at__isnull=True).exists())
        with self.assertRaises(PermissionDenied):
            board.snapshot(actor=self.child, session_id=session.pk)
        self.assertTrue(Enrollment.objects.filter(user=self.child, course=self.course).exists())
        self.assertFalse(course_allowed(self.child, self.course))

    def test_whole_guardian_revocation_denies_stale_objects_and_learning_progress_access(self):
        room, session, participant = self.live_class()
        self.grant_contact(calls=True)
        conversation = self.historical_room(self.adult, self.child)
        revoke_guardian(actor=self.guardian, authorization_id=self.authorization.pk)
        self.assertFalse(course_allowed(self.child, self.course, live=True))
        self.assertFalse(can_access(self.adult, conversation.pk))
        self.assertEqual(self.api(self.guardian).get(f"/api/auth/guardians/{self.authorization.pk}/learning/").status_code, 403)

    def test_minimum_age_cannot_be_overridden_by_guardian_or_role(self):
        self.grant_course(live=True)
        self.course.minimum_age = 18
        self.course.save(update_fields=["minimum_age"])
        self.assertFalse(course_allowed(self.child, self.course))
        self.assertFalse(course_allowed(self.teen, self.course))
        self.assertTrue(course_allowed(self.adult, self.course))
        self.assertEqual(self.api(self.teen).get(f"/api/learning/lessons/{self.lesson.pk}/").status_code, 403)

    def test_attachment_and_profile_media_cannot_bypass_contact_revocation(self):
        from config.media_views import _media_is_allowed
        self.grant_contact()
        room = self.historical_room(self.adult, self.child)
        Message.objects.filter(conversation=room).update(file="messages/files/child-private.pdf")
        User.objects.filter(pk=self.child.pk).update(profile_picture="profiles/child-private.png")
        self.assertTrue(_media_is_allowed(self.adult, "messages/files/child-private.pdf"))
        change_permission(actor=self.guardian, authorization_id=self.authorization.pk, action="remove_contact", data={"username": self.adult.username})
        self.assertFalse(_media_is_allowed(self.adult, "messages/files/child-private.pdf"))
        self.assertFalse(_media_is_allowed(self.adult, "profiles/child-private.png"))

    def test_unsolicited_notifications_and_minor_location_search_are_suppressed(self):
        from notifications.models import Notification
        from notifications.age_safety import visible_notifications
        notification = Notification.objects.create(user=self.child, sender=self.adult, notification_type="MESSAGE", message="unsolicited")
        self.assertFalse(visible_notifications(Notification.objects.filter(user=self.child)).filter(pk=notification.pk).exists())
        self.grant_contact()
        from accounts.age_safety import searchable_profiles
        self.assertFalse(searchable_profiles(self.adult, TalentProfile.objects.all()).filter(pk=self.profile.pk).exists())
        self.assertTrue(searchable_profiles(self.guardian, TalentProfile.objects.all()).filter(pk=self.profile.pk).exists())

    def test_guardian_catalog_and_progress_are_scoped_and_preserve_child_creator_workflow(self):
        draft = Course.objects.create(creator=self.child, category=self.category, title="Child's draft", slug="child-draft", status="DRAFT", is_free=True)
        result = self.api(self.guardian).get(f"/api/auth/guardians/{self.authorization.pk}/courses/")
        self.assertEqual(result.status_code, 200, result.data)
        rows = result.data if isinstance(result.data, list) else result.data["results"]
        self.assertIn(draft.pk, [row["id"] for row in rows])
        change_permission(actor=self.guardian, authorization_id=self.authorization.pk, action="allow_course", data={"course_id": draft.pk})
        self.assertTrue(course_allowed(self.child, draft))
        self.assertEqual(self.api(self.adult).get(f"/api/auth/guardians/{self.authorization.pk}/learning/").status_code, 404)

    def test_guardian_cannot_read_private_data_or_suspend_account_after_adulthood(self):
        from accounts.age_safety import guardian_of
        from accounts.age_policy import age_access_allowed
        User.objects.filter(pk=self.child.pk).update(date_of_birth=date(2000, 1, 1))
        self.child.refresh_from_db()
        self.assertFalse(guardian_of(self.guardian, self.child))
        with self.assertRaises(PermissionDenied):
            revoke_guardian(actor=self.guardian, authorization_id=self.authorization.pk)
        self.assertTrue(age_access_allowed(self.child))
        self.assertEqual(self.api(self.guardian).get(f"/api/auth/guardians/{self.authorization.pk}/learning/").status_code, 404)


class AgeDeliveryBoundaryTests(SimpleTestCase):
    def test_permission_is_checked_at_send_boundary_after_credentials_await(self):
        from messaging.consumers import UserConsumer
        from channels.generic.websocket import AsyncWebsocketConsumer
        consumer = UserConsumer()
        consumer.credentials_valid = AsyncMock(return_value=True)
        consumer.messaging_access = AsyncMock(return_value=False)
        consumer.close = AsyncMock()
        with patch.object(AsyncWebsocketConsumer, "send", new_callable=AsyncMock) as transport:
            async_to_sync(consumer.send_checked)("conversation", 1, text_data='{"content":"must not arrive"}')
        transport.assert_not_awaited()
        consumer.close.assert_awaited_once_with(code=4003)


@override_settings(ALLOWED_HOSTS=["testserver"], MESSAGING_WS_HEARTBEAT_SECONDS=0.05,
                   CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class AgeFeatureSocketTests(AgeFeatureFixture, TransactionTestCase):
    def test_classroom_and_whiteboard_sockets_close_on_live_permission_withdrawal(self):
        from config.asgi import application
        _, session, _ = self.live_class()
        token = str(AccessToken.for_user(self.child))
        async def run():
            headers = [(b"authorization", ("Bearer " + token).encode())]
            classroom = WebsocketCommunicator(application, f"/ws/learning/sessions/{session.pk}/?connection_id={uuid4()}", headers=headers)
            whiteboard = WebsocketCommunicator(application, f"/ws/learning/sessions/{session.pk}/whiteboard/", headers=headers)
            self.assertTrue((await classroom.connect(timeout=5))[0])
            await classroom.receive_json_from(timeout=5)
            self.assertTrue((await whiteboard.connect(timeout=5))[0])
            await whiteboard.receive_json_from(timeout=5)
            await database_sync_to_async(change_permission)(actor=self.guardian, authorization_id=self.authorization.pk,
                action="remove_course", data={"course_id": self.course.pk})
            for socket in (classroom, whiteboard):
                for _ in range(5):
                    result = await socket.receive_output(timeout=5)
                    if result["type"] == "websocket.close":
                        self.assertEqual(result["code"], 4403)
                        break
                else:
                    self.fail("Revoked classroom socket did not close.")
                await socket.disconnect()
        async_to_sync(run)()

    def test_idle_user_socket_closes_on_guardian_revocation(self):
        from config.asgi import application
        token = str(AccessToken.for_user(self.child))
        async def run():
            socket = WebsocketCommunicator(application, "/ws/user/", headers=[(b"authorization", ("Bearer " + token).encode())])
            self.assertTrue((await socket.connect(timeout=5))[0])
            await socket.receive_json_from(timeout=5)
            await database_sync_to_async(revoke_guardian)(actor=self.guardian, authorization_id=self.authorization.pk)
            self.assertEqual((await socket.receive_output(timeout=5))["code"], 4001)
            await socket.disconnect()
        async_to_sync(run)()

    def test_existing_call_socket_cannot_signal_after_contact_permission_withdrawal(self):
        from config.asgi import application
        self.grant_contact(calls=True)
        room = self.historical_room(self.adult, self.child)
        call = Call.objects.create(conversation=room, initiated_by=self.adult, call_type="VOICE", status="ACTIVE")
        CallParticipant.objects.create(call=call, user=self.adult, status="JOINED")
        CallParticipant.objects.create(call=call, user=self.child, status="JOINED")
        token = str(AccessToken.for_user(self.adult))
        async def run():
            socket = WebsocketCommunicator(application, f"/ws/calls/{call.pk}/", headers=[(b"authorization", ("Bearer " + token).encode())])
            self.assertTrue((await socket.connect(timeout=5))[0])
            await socket.receive_json_from(timeout=5)
            await database_sync_to_async(change_permission)(actor=self.guardian, authorization_id=self.authorization.pk,
                action="remove_contact", data={"username": self.adult.username})
            # Ending the call can send an end frame before its close; no subsequent SDP is authorized.
            output = await socket.receive_output(timeout=5)
            if output["type"] == "websocket.send":
                output = await socket.receive_output(timeout=5)
            self.assertEqual(output["type"], "websocket.close")
            await socket.disconnect()
        async_to_sync(run)()

import json
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase, override_settings
from notifications.models import MobilePushToken, Notification
from notifications.services import create_notification

from . import classroom_services as services
from .classroom_notifications import classroom_notification_is_current, notify_session_event
from .models import ClassroomMembership, Enrollment, LiveSession
from .test_classroom_security import ClassroomFixture


class ClassroomNotificationTests(ClassroomFixture, TestCase):
    def setUp(self):
        super().setUp()
        ClassroomMembership.objects.create(classroom=self.classroom, user=self.learner)

    def notices(self, session, event):
        return Notification.objects.filter(notification_type="CLASSROOM_SESSION",
            metadata__session_id=session.pk, metadata__event=event)

    def test_scheduling_notifies_eligible_class_members_without_auto_admission(self):
        session = self.schedule()
        recipients = set(self.notices(session, "SCHEDULED").values_list("user_id", flat=True))
        self.assertEqual(recipients, {self.host.pk, self.cohost.pk, self.learner.pk})
        self.assertNotIn(self.other.pk, recipients)
        self.assertFalse(session.participants.filter(membership__user=self.learner).exists())

    def test_start_end_and_cancel_are_notified_once_per_user(self):
        session = self.schedule()
        services.start_session(actor=self.host, session=session)
        services.start_session(actor=self.host, session=session)
        self.assertEqual(self.notices(session, "STARTED").count(), 3)
        services.end_session(actor=self.host, session=session)
        services.end_session(actor=self.host, session=session)
        self.assertEqual(self.notices(session, "ENDED").count(), 3)
        scheduled = self.schedule()
        services.cancel_session(actor=self.host, session=scheduled)
        services.cancel_session(actor=self.host, session=scheduled)
        self.assertEqual(self.notices(scheduled, "CANCELLED").count(), 3)
        # Reprocessing the notification hook also does not create duplicates.
        notify_session_event(actor=self.host, session=session, event="ENDED")
        self.assertEqual(self.notices(session, "ENDED").count(), 3)

    def test_inactive_and_unenrolled_learners_are_not_notified(self):
        Enrollment.objects.filter(user=self.learner).delete()
        session = self.schedule()
        self.assertFalse(self.notices(session, "SCHEDULED").filter(user=self.learner).exists())
        Enrollment.objects.create(user=self.learner, course=self.course)
        ClassroomMembership.objects.filter(classroom=self.classroom, user=self.learner).update(is_active=False)
        session = self.schedule()
        self.assertFalse(self.notices(session, "SCHEDULED").filter(user=self.learner).exists())

    def test_removed_participants_are_excluded_from_lifecycle_notifications(self):
        target = services.request_admission(actor=self.learner, session=self.session)
        services.remove_participant(actor=self.host, session=self.session, participant=target)
        services.end_session(actor=self.host, session=self.session)
        self.assertFalse(self.notices(self.session, "ENDED").filter(user=self.learner).exists())

    def test_unauthorized_and_failed_transitions_do_not_create_notifications(self):
        count = Notification.objects.count()
        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            services.end_session(actor=self.learner, session=self.session)
        with patch("learning.classroom_notifications.notification_services.create_notification", side_effect=RuntimeError("failed")):
            with self.assertRaises(RuntimeError):
                services.end_session(actor=self.host, session=self.session)
        self.assertEqual(Notification.objects.count(), count)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "LIVE")
        self.assertFalse(self.session.audit_events.filter(event_type="ENDED").exists())

    def test_scheduling_and_push_callbacks_roll_back_together(self):
        before = LiveSession.objects.count()
        with patch("notifications.signals.publish_notification") as publish:
            with self.captureOnCommitCallbacks(execute=True):
                with self.assertRaises(RuntimeError), transaction.atomic():
                    self.schedule()
                    raise RuntimeError("rollback")
            publish.assert_not_called()
        self.assertEqual(LiveSession.objects.count(), before)

    def test_scheduling_uses_existing_after_commit_delivery_signal(self):
        with patch("notifications.signals.publish_notification") as publish:
            with self.captureOnCommitCallbacks(execute=True):
                session = self.schedule()
            self.assertEqual(publish.call_count, self.notices(session, "SCHEDULED").count())
            self.assertEqual({call.args[0] for call in publish.call_args_list}, set(self.notices(session, "SCHEDULED").values_list("pk", flat=True)))

    def test_stale_notifications_are_suppressed_after_access_revocation(self):
        session = self.schedule()
        notice = self.notices(session, "SCHEDULED").get(user=self.learner)
        self.assertTrue(classroom_notification_is_current(notice))
        Enrollment.objects.filter(user=self.learner).delete()
        self.assertFalse(classroom_notification_is_current(notice))
        from notifications.signals import publish_notification
        with patch("notifications.push.send_push_notification") as web, patch("notifications.push.send_expo_classroom_push") as expo:
            publish_notification(notice.pk)
        web.assert_not_called()
        expo.assert_not_called()

    def test_native_push_reuses_registry_and_contains_only_safe_routing_metadata(self):
        from notifications.push import notification_payload, send_expo_classroom_push
        session = self.schedule()
        notice = self.notices(session, "SCHEDULED").get(user=self.learner)
        notice.metadata["secret"] = "private-data"
        MobilePushToken.objects.create(user=self.learner, token="ExponentPushToken[classroom-device]", platform="ios")
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps({"data": [{"status": "ok"}]}).encode()
        with patch("notifications.push.urlopen", return_value=response) as send:
            send_expo_classroom_push(notice)
        payload = json.loads(send.call_args.args[0].data)[0]
        self.assertEqual(payload["to"], "ExponentPushToken[classroom-device]")
        self.assertEqual(payload["data"]["session_id"], session.pk)
        self.assertEqual(payload["data"]["type"], "classroom_session")
        self.assertNotIn("secret", payload["data"])
        self.assertNotIn("secret", notification_payload(notice)["data"])
        self.assertNotIn("channelId", payload)

    def test_native_push_removes_unregistered_tokens_and_skips_unrelated_types(self):
        from notifications.push import send_expo_classroom_push
        session = self.schedule()
        notice = self.notices(session, "SCHEDULED").get(user=self.learner)
        MobilePushToken.objects.create(user=self.learner, token="ExponentPushToken[expired-classroom]", platform="android")
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps({"data": [{"status": "error", "details": {"error": "DeviceNotRegistered"}}]}).encode()
        with patch("notifications.push.urlopen", return_value=response):
            send_expo_classroom_push(notice)
        self.assertFalse(MobilePushToken.objects.filter(user=self.learner).exists())
        plain = Notification.objects.create(user=self.learner, notification_type="SYSTEM", message="Plain")
        with patch("notifications.push.urlopen") as send:
            send_expo_classroom_push(plain)
        send.assert_not_called()

    def test_invitation_push_is_suppressed_after_decline(self):
        recipient = get_user_model().objects.create_user(username="push-invited")
        invitation, _ = services.invite_classroom_user(actor=self.host, classroom=self.classroom, recipient=recipient)
        notice = Notification.objects.get(user=recipient, notification_type="CLASSROOM_INVITATION")
        self.assertTrue(classroom_notification_is_current(notice))
        services.decline_classroom_invitation(actor=recipient, invitation=invitation)
        self.assertFalse(classroom_notification_is_current(notice))

    def test_central_notification_deduplication_preserves_existing_behavior(self):
        args = dict(user=self.learner, sender=self.host, message="One event", deduplication_key="test:classroom-event")
        first = create_notification(**args)
        second = create_notification(**args)
        self.assertEqual(first.pk, second.pk)
        self.assertIsNone(create_notification(user=self.host, sender=self.host, message="Self"))
        plain = create_notification(user=self.learner, message="Unkeyed")
        another = create_notification(user=self.learner, message="Unkeyed")
        self.assertNotEqual(plain.pk, another.pk)

    @override_settings(EXPO_PUSH_ACCESS_TOKEN="classroom-test-access-token")
    def test_native_push_batches_devices_and_reuses_access_token(self):
        from notifications.push import send_expo_classroom_push
        session = self.schedule()
        notice = self.notices(session, "SCHEDULED").get(user=self.learner)
        MobilePushToken.objects.bulk_create([
            MobilePushToken(user=self.learner, token=f"ExponentPushToken[classroom-{number}]", platform="android")
            for number in range(101)])
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"data": []}'
        with patch("notifications.push.urlopen", return_value=response) as send:
            send_expo_classroom_push(notice)
        self.assertEqual(send.call_count, 2)
        requests = [call.args[0] for call in send.call_args_list]
        self.assertEqual([len(json.loads(request.data)) for request in requests], [100, 1])
        self.assertTrue(all(request.get_header("Authorization") == "Bearer classroom-test-access-token" for request in requests))

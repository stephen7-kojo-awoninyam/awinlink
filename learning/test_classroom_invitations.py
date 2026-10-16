from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, models, transaction
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone
from rest_framework.test import APITestCase

from notifications.models import Notification

from . import classroom_services as services
from .models import ClassroomInvitation, ClassroomMembership, Enrollment
from .test_classroom_security import ClassroomFixture
from . import test_classroom_security as security_tests


class InvitationFixture(ClassroomFixture):
    def setUp(self):
        super().setUp()
        self.recipient = get_user_model().objects.create_user(username="invited-new-learner")

    def invite(self, actor=None, recipient=None, **kwargs):
        invitation, created = services.invite_classroom_user(actor=actor or self.host, classroom=self.classroom,
            recipient=recipient or self.recipient, **kwargs)
        return invitation, created


class ClassroomInvitationServiceTests(InvitationFixture, TestCase):
    def test_invitation_does_not_enroll_or_grant_membership_without_consent(self):
        invitation, created = self.invite(message="Please join.")
        self.assertTrue(created)
        self.assertEqual(invitation.status, "PENDING")
        self.assertFalse(Enrollment.objects.filter(user=self.recipient).exists())
        self.assertFalse(self.classroom.memberships.filter(user=self.recipient).exists())
        notification = Notification.objects.get(user=self.recipient, notification_type="CLASSROOM_INVITATION")
        self.assertEqual(notification.metadata["invitation_id"], invitation.pk)

    def test_host_permissions_and_scope_are_required(self):
        for actor in [self.learner, self.cohost, self.other, self.admin]:
            with self.assertRaises(PermissionDenied):
                self.invite(actor=actor)
        other_room = services.create_classroom(actor=self.creator, course=self.course, title="Other")
        with self.assertRaises(PermissionDenied):
            services.invite_classroom_user(actor=self.host, classroom=other_room, recipient=self.recipient)
        self.invite(actor=self.creator)

    def test_duplicate_invites_are_idempotent_and_notify_once(self):
        first, _ = self.invite()
        second, created = self.invite(actor=self.creator, message="Changed")
        self.assertFalse(created)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(second.invited_by_id, self.host.pk)
        self.assertEqual(ClassroomInvitation.objects.filter(classroom=self.classroom, recipient=self.recipient).count(), 1)
        self.assertEqual(Notification.objects.filter(user=self.recipient, notification_type="CLASSROOM_INVITATION").count(), 1)
        self.assertEqual(self.classroom.audit_events.filter(event_type="CLASSROOM_INVITED").count(), 1)

    def test_accept_enrolls_as_learner_without_session_admission(self):
        invitation, _ = self.invite()
        result = services.accept_classroom_invitation(actor=self.recipient, invitation=invitation)
        self.assertEqual(result.status, "ACCEPTED")
        self.assertEqual(self.classroom.memberships.get(user=self.recipient).role, "LEARNER")
        self.assertTrue(Enrollment.objects.filter(user=self.recipient, course=self.course).exists())
        self.assertFalse(self.session.participants.filter(membership__user=self.recipient).exists())
        target = services.request_admission(actor=self.recipient, session=self.session)
        self.assertEqual(target.admission_state, "WAITING")
        from uuid import uuid4
        with self.assertRaises(PermissionDenied):
            services.join_session(actor=self.recipient, session=self.session, connection_id=uuid4())
        before = Notification.objects.count()
        services.accept_classroom_invitation(actor=self.recipient, invitation=invitation)
        self.assertEqual(Notification.objects.count(), before)

    def test_only_recipient_may_accept_or_decline(self):
        invitation, _ = self.invite()
        for actor in [self.host, self.creator, self.other, self.admin]:
            for operation in [services.accept_classroom_invitation, services.decline_classroom_invitation]:
                with self.assertRaises(PermissionDenied):
                    operation(actor=actor, invitation=invitation)
        self.assertFalse(Enrollment.objects.filter(user=self.recipient).exists())

    def test_decline_is_final_and_does_not_enroll(self):
        invitation, _ = self.invite()
        result = services.decline_classroom_invitation(actor=self.recipient, invitation=invitation)
        self.assertEqual(result.status, "DECLINED")
        before = Notification.objects.count()
        services.decline_classroom_invitation(actor=self.recipient, invitation=invitation)
        self.assertEqual(Notification.objects.count(), before)
        self.assertFalse(Enrollment.objects.filter(user=self.recipient).exists())
        with self.assertRaises(ValidationError):
            services.accept_classroom_invitation(actor=self.recipient, invitation=invitation)
        new, created = self.invite()
        self.assertTrue(created)
        self.assertNotEqual(new.pk, invitation.pk)

    def test_revocation_blocks_acceptance(self):
        invitation, _ = self.invite()
        with self.assertRaises(PermissionDenied):
            services.revoke_classroom_invitation(actor=self.cohost, invitation=invitation)
        services.revoke_classroom_invitation(actor=self.creator, invitation=invitation)
        with self.assertRaises(ValidationError):
            services.accept_classroom_invitation(actor=self.recipient, invitation=invitation)

    def test_expired_invitations_cannot_be_used_and_can_be_reissued(self):
        now = timezone.now()
        invitation, _ = self.invite(expires_at=now + timedelta(hours=1))
        with patch("learning.classroom_services.timezone.now", return_value=now + timedelta(hours=2)):
            with self.assertRaises(ValidationError):
                services.accept_classroom_invitation(actor=self.recipient, invitation=invitation)
            new, created = self.invite()
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "EXPIRED")
        self.assertTrue(created)
        self.assertNotEqual(new.pk, invitation.pk)

    def test_inactive_accounts_memberships_and_unapproved_courses_block_invites(self):
        get_user_model().objects.filter(pk=self.recipient.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.invite()
        get_user_model().objects.filter(pk=self.recipient.pk).update(is_active=True)
        ClassroomMembership.objects.create(classroom=self.classroom, user=self.recipient, is_active=False)
        with self.assertRaises(PermissionDenied):
            self.invite()
        self.course.status = "DRAFT"
        self.course.save()
        with self.assertRaises(ValidationError):
            self.invite(recipient=self.other)

    def test_pending_invitation_cannot_restore_blocked_membership_or_revoked_host(self):
        invitation, _ = self.invite()
        member = ClassroomMembership.objects.create(classroom=self.classroom, user=self.recipient, is_active=False)
        with self.assertRaises(PermissionDenied):
            services.accept_classroom_invitation(actor=self.recipient, invitation=invitation)
        member.delete()
        self.classroom.memberships.filter(user=self.host).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            services.accept_classroom_invitation(actor=self.recipient, invitation=invitation)
        services.decline_classroom_invitation(actor=self.recipient, invitation=invitation)

    def test_accept_retry_cannot_recreate_revoked_enrollment(self):
        invitation, _ = self.invite()
        services.accept_classroom_invitation(actor=self.recipient, invitation=invitation)
        Enrollment.objects.filter(user=self.recipient).delete()
        with self.assertRaises(PermissionDenied):
            services.accept_classroom_invitation(actor=self.recipient, invitation=invitation)
        self.assertFalse(Enrollment.objects.filter(user=self.recipient).exists())

    def test_existing_staff_and_members_cannot_be_reinvited_or_demoted(self):
        for recipient in [self.creator, self.host, self.cohost]:
            with self.assertRaises((PermissionDenied, ValidationError)):
                self.invite(recipient=recipient)
        invitation, _ = self.invite()
        services.accept_classroom_invitation(actor=self.recipient, invitation=invitation)
        with self.assertRaises(ValidationError):
            self.invite()

    def test_notification_or_audit_failures_roll_back_acceptance(self):
        invitation, _ = self.invite()
        for target in ["learning.classroom_services._audit", "learning.classroom_notifications.notification_services.create_notification"]:
            with patch(target, side_effect=RuntimeError("failed")):
                with self.assertRaises(RuntimeError):
                    services.accept_classroom_invitation(actor=self.recipient, invitation=invitation)
            invitation.refresh_from_db()
            self.assertEqual(invitation.status, "PENDING")
            self.assertFalse(Enrollment.objects.filter(user=self.recipient).exists())
            self.assertFalse(self.classroom.memberships.filter(user=self.recipient).exists())

    def test_model_bulk_writes_and_database_constraints_protect_invitation_integrity(self):
        invitation, _ = self.invite()
        with self.assertRaises(ValidationError):
            ClassroomInvitation.objects.filter(pk=invitation.pk).update(recipient=self.other)
        with self.assertRaises(ValidationError):
            ClassroomInvitation.objects.filter(pk=invitation.pk).update(status="ACCEPTED")
        with self.assertRaises(IntegrityError), transaction.atomic():
            models.QuerySet(model=ClassroomInvitation, using="default").bulk_create([
                ClassroomInvitation(classroom=self.classroom, recipient=self.recipient, invited_by=self.host,
                                    expires_at=timezone.now() + timedelta(days=1))])
        services.decline_classroom_invitation(actor=self.recipient, invitation=invitation)
        with self.assertRaises(ValidationError):
            ClassroomInvitation.objects.filter(pk=invitation.pk).update(status="PENDING", responded_at=None)

    def test_invitation_delivery_waits_for_commit_and_is_discarded_on_rollback(self):
        with patch("notifications.signals.publish_notification") as publish:
            with self.captureOnCommitCallbacks(execute=True):
                self.invite()
                self.invite()
            publish.assert_called_once()
            publish.reset_mock()
            with self.captureOnCommitCallbacks(execute=True):
                with self.assertRaises(RuntimeError), transaction.atomic():
                    self.invite(recipient=self.other)
                    raise RuntimeError("rollback")
            publish.assert_not_called()
            self.assertFalse(ClassroomInvitation.objects.filter(recipient=self.other).exists())


class ClassroomInvitationAPITests(InvitationFixture, APITestCase):
    def setUp(self):
        super().setUp()
        self.outgoing = f"/api/learning/classrooms/{self.classroom.pk}/invitations/"
        self.incoming = "/api/learning/classroom-invitations/"

    def test_authentication_and_host_only_creation(self):
        self.assertEqual(self.client.get(self.incoming).status_code, 401)
        self.assertEqual(self.client.post(self.outgoing, {"recipient": self.recipient.pk}, format="json").status_code, 401)
        for user in [self.learner, self.cohost, self.admin]:
            self.client.force_authenticate(user=user)
            response = self.client.post(self.outgoing, {"recipient": self.recipient.pk}, format="json")
            self.assertIn(response.status_code, [403, 404])
            self.assertIn("error", response.data)

    def test_create_duplicate_list_and_recipient_accept(self):
        self.client.force_authenticate(user=self.host)
        first = self.client.post(self.outgoing, {"recipient": self.recipient.pk, "message": "Welcome"}, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        duplicate = self.client.post(self.outgoing, {"recipient": self.recipient.pk}, format="json")
        self.assertEqual(duplicate.status_code, 200, duplicate.data)
        self.assertEqual(first.data["id"], duplicate.data["id"])
        self.assertEqual(self.client.get(self.outgoing).data["count"], 1)
        self.client.force_authenticate(user=self.recipient)
        self.assertEqual(self.client.get(self.incoming).data["count"], 1)
        detail = self.incoming + f"{first.data['id']}/"
        self.assertEqual(self.client.get(detail).status_code, 200)
        self.assertEqual(self.client.post(detail + "accept/", {}, format="json").data["status"], "ACCEPTED")
        response = self.client.post(f"/api/learning/sessions/{self.session.pk}/join/", {"connection_id": "ec802d06-1c1e-4cbb-ae41-98da6c33d985"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_recipient_scope_cannot_be_overridden_by_ids_or_query_parameters(self):
        invitation, _ = self.invite()
        for user in [self.other, self.admin, self.host]:
            self.client.force_authenticate(user=user)
            self.assertEqual(self.client.get(self.incoming + f"?recipient={self.recipient.pk}").data["count"], 0)
            for suffix, method in [("", "get"), ("accept/", "post"), ("decline/", "post")]:
                url = self.incoming + f"{invitation.pk}/" + suffix
                response = self.client.get(url) if method == "get" else self.client.post(url, {}, format="json")
                self.assertEqual(response.status_code, 404)

    def test_injected_roles_statuses_and_actors_are_rejected(self):
        self.client.force_authenticate(user=self.host)
        for key, value in {"role": "HOST", "status": "ACCEPTED", "invited_by": self.admin.pk}.items():
            response = self.client.post(self.outgoing, {"recipient": self.recipient.pk, key: value}, format="json")
            self.assertEqual(response.status_code, 400)
        invitation, _ = self.invite()
        self.client.force_authenticate(user=self.recipient)
        response = self.client.post(self.incoming + f"{invitation.pk}/accept/", {"role": "HOST"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Enrollment.objects.filter(user=self.recipient).exists())

    def test_decline_revoke_and_get_cannot_accept(self):
        invitation, _ = self.invite()
        self.client.force_authenticate(user=self.recipient)
        detail = self.incoming + f"{invitation.pk}/"
        self.assertEqual(self.client.get(detail + "accept/").status_code, 405)
        self.assertEqual(self.client.post(detail + "decline/", {}, format="json").data["status"], "DECLINED")
        invitation, _ = self.invite()
        self.client.force_authenticate(user=self.host)
        self.assertEqual(self.client.post(self.outgoing + f"{invitation.pk}/revoke/", {}, format="json").data["status"], "REVOKED")
        self.client.force_authenticate(user=self.recipient)
        self.assertEqual(self.client.post(self.incoming + f"{invitation.pk}/accept/", {}, format="json").status_code, 400)

    def test_notification_api_exposes_only_owned_routing_metadata(self):
        invitation, _ = self.invite()
        self.client.force_authenticate(user=self.recipient)
        response = self.client.get("/api/notifications/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["metadata"]["invitation_id"], invitation.pk)
        self.assertNotIn("deduplication_key", response.data[0])
        self.assertNotIn("recipient", response.data[0]["metadata"])


class ClassroomInvitationConcurrencyTests(InvitationFixture, TransactionTestCase):
    race = security_tests.ClassroomConcurrencyTests.race

    def setUp(self):
        delivery = patch("notifications.signals.publish_notification")
        delivery.start()
        self.addCleanup(delivery.stop)
        super().setUp()

    @skipUnlessDBFeature("has_select_for_update")
    def test_simultaneous_invites_create_one_invitation_and_one_notification(self):
        with patch("notifications.signals.publish_notification"):
            outcomes = self.race(lambda: self.invite(), lambda: self.invite(actor=self.creator))
        self.assertEqual({value[0].pk for value in outcomes}, {ClassroomInvitation.objects.get(recipient=self.recipient).pk})
        self.assertEqual(Notification.objects.filter(user=self.recipient, notification_type="CLASSROOM_INVITATION").count(), 1)

    @skipUnlessDBFeature("has_select_for_update")
    def test_accept_decline_race_has_one_final_state_and_consistent_membership(self):
        invitation, _ = self.invite()
        self.race(lambda: services.accept_classroom_invitation(actor=self.recipient, invitation=invitation),
                  lambda: services.decline_classroom_invitation(actor=self.recipient, invitation=invitation))
        invitation.refresh_from_db()
        self.assertIn(invitation.status, {"ACCEPTED", "DECLINED"})
        self.assertEqual(Enrollment.objects.filter(user=self.recipient).exists(), invitation.status == "ACCEPTED")
        self.assertEqual(self.classroom.memberships.filter(user=self.recipient).exists(), invitation.status == "ACCEPTED")
        self.assertEqual(Notification.objects.filter(user=self.host, metadata__invitation_id=invitation.pk).count(), 1)

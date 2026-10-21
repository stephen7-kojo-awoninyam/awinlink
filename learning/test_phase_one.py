from datetime import timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase
from . import classroom_services as services
from .models import AdmissionState, ClassroomMembership, ClassroomRole, LiveSession
from .test_classroom_security import ClassroomFixture


class PhaseOneTests(ClassroomFixture, APITestCase):
    def setUp(self):
        super().setUp()
        services.end_session(actor=self.host, session=self.session)
        self.scheduled = self.schedule()
        self.url = f'/api/learning/classrooms/{self.classroom.pk}/staff/'

    def test_staff_access_is_creator_only(self):
        for user in [self.host, self.cohost, self.learner, self.admin]:
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get(self.url).status_code, 404 if user == self.admin else 403)
            self.assertEqual(self.client.post(self.url, {'user': self.other.pk, 'role': 'COHOST'}, format='json').status_code, 404 if user == self.admin else 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_assign_remove_restore_and_transfer(self):
        self.client.force_authenticate(self.creator)
        def write(user, role):
            return self.client.post(self.url, {'user': user.pk, 'role': role}, format='json')
        self.assertEqual(write(self.other, 'COHOST').status_code, 200)
        participant = self.scheduled.participants.get(membership__user=self.other)
        self.assertEqual(participant.admission_state, AdmissionState.ADMITTED)
        self.assertEqual(write(self.other, 'REMOVE').status_code, 204)
        participant.refresh_from_db()
        self.assertEqual(participant.admission_state, AdmissionState.REMOVED)
        self.assertFalse(ClassroomMembership.objects.get(classroom=self.classroom, user=self.other).is_active)
        self.assertEqual(write(self.other, 'COHOST').status_code, 200)
        participant.refresh_from_db()
        self.assertEqual(participant.admission_state, AdmissionState.ADMITTED)
        self.assertEqual(write(self.other, 'HOST').status_code, 200)
        self.assertEqual(ClassroomMembership.objects.get(classroom=self.classroom, user=self.host).role, ClassroomRole.COHOST)
        participant.refresh_from_db()
        self.assertEqual(participant.role, ClassroomRole.HOST)
        self.assertEqual(write(self.other, 'REMOVE').status_code, 403)
        self.assertEqual(write(self.other, 'COHOST').status_code, 400)

    def test_live_session_blocks_staff_changes_and_unknown_fields(self):
        self.client.force_authenticate(self.creator)
        services.start_session(actor=self.host, session=self.scheduled)
        for role in ['COHOST', 'HOST', 'REMOVE']:
            response = self.client.post(self.url, {'user': self.cohost.pk, 'role': role}, format='json')
            self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(self.client.post(self.url, {'user': self.other.pk, 'role': 'COHOST', 'is_active': True}, format='json').status_code, 400)

    def test_capabilities_match_creator_host_and_learner(self):
        url = f'/api/learning/classrooms/{self.classroom.pk}/'
        for user, expected in [(self.creator, {'manage': True, 'staff': True}), (self.host, {'manage': True, 'staff': False}), (self.learner, {'manage': False, 'staff': False})]:
            self.client.force_authenticate(user)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['capabilities'], expected)

    def test_creator_can_create_then_schedule_and_invite(self):
        self.client.force_authenticate(self.creator)
        room = self.client.post('/api/learning/classrooms/', {'course': self.course.pk, 'title': 'New room', 'capacity': 10}, format='json')
        self.assertEqual(room.status_code, 201, room.data)
        self.assertTrue(room.data['capabilities']['staff'])
        base = f"/api/learning/classrooms/{room.data['id']}/"
        start = timezone.now() + timedelta(days=1)
        response = self.client.post(base + 'sessions/', {'lesson': self.lesson.pk, 'title': 'New session', 'scheduled_start': start.isoformat(), 'scheduled_end': (start + timedelta(hours=1)).isoformat()}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        recipient = get_user_model().objects.create_user(username='phase-one-recipient')
        invitation = self.client.post(base + 'invitations/', {'recipient': recipient.pk, 'message': 'Join us'}, format='json')
        self.assertEqual(invitation.status_code, 201, invitation.data)
        self.client.force_authenticate(recipient)
        inbox = self.client.get('/api/learning/classroom-invitations/')
        self.assertEqual(inbox.data['results'][0]['id'], invitation.data['id'])
        accepted = self.client.post(f"/api/learning/classroom-invitations/{invitation.data['id']}/accept/", {}, format='json')
        self.assertEqual(accepted.status_code, 200, accepted.data)
        self.assertEqual(self.client.get(base).status_code, 200)

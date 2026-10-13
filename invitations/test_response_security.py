from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse, resolve

from domains.models import TalentDomain
from messaging.models import Conversation
from opportunities.models import Opportunity
from organizations.models import Organization
from recruitment.models import RecruitmentStage
from talents.models import TalentProfile
from .models import Invitation


class InvitationResponseSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(username='invite_audit_owner', role='ORGANIZATION')
        cls.recipient = User.objects.create_user(username='invite_audit_recipient', role='ATHLETE')
        cls.outsider = User.objects.create_user(username='invite_audit_outsider', role='ATHLETE')
        cls.organization = Organization.objects.create(user=cls.owner, name='Invitation audit', country='GH')
        cls.talent = TalentProfile.objects.create(user=cls.recipient)
        domain = TalentDomain.objects.create(name='Invitation audit domain')
        cls.opportunity = Opportunity.objects.create(organization=cls.organization, domain=domain, title='Invitation audit opportunity')

    def setUp(self):
        self.invitation = Invitation.objects.create(organization=self.organization, talent=self.talent, opportunity=self.opportunity)
        self.browser = Client(enforce_csrf_checks=True)
        self.browser.force_login(self.recipient)
        self.browser.get(reverse('login'))
        self.csrf = self.browser.cookies['csrftoken'].value

    def respond(self, route):
        return self.browser.post(reverse(route, args=[self.invitation.pk]), {'csrfmiddlewaretoken': self.csrf})

    def test_get_and_csrf_less_post_cannot_change_either_response(self):
        for route in ('accept_invitation', 'decline_invitation'):
            url = reverse(route, args=[self.invitation.pk])
            self.assertEqual(self.browser.get(url).status_code, 405)
            self.assertEqual(self.browser.post(url).status_code, 403)
            self.invitation.refresh_from_db()
            self.assertEqual(self.invitation.status, 'PENDING')

    def test_accept_creates_participating_conversation_and_cannot_be_replayed(self):
        self.assertEqual(self.respond('accept_invitation').status_code, 302)
        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.status, 'ACCEPTED')
        self.assertIsNotNone(self.invitation.responded_at)
        conversation = Conversation.objects.get(opportunity=self.opportunity)
        self.assertEqual(set(conversation.participants.values_list('user_id', flat=True)), {self.owner.pk, self.recipient.pk})
        self.assertEqual(RecruitmentStage.objects.get(talent=self.talent).stage, 'INTERVIEW')
        self.assertEqual(self.respond('accept_invitation').status_code, 400)
        self.assertEqual(self.respond('decline_invitation').status_code, 400)
        self.assertEqual(Conversation.objects.count(), 1)

    def test_decline_records_response_and_rejects_nonrecipient(self):
        self.browser.force_login(self.outsider)
        self.assertEqual(self.respond('decline_invitation').status_code, 404)
        self.browser.force_login(self.recipient)
        self.assertEqual(self.respond('decline_invitation').status_code, 302)
        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.status, 'DECLINED')
        self.assertIsNotNone(self.invitation.responded_at)

    def test_failure_rolls_back_acceptance_and_recruitment_changes(self):
        with patch('invitations.views.Conversation.objects.create', side_effect=RuntimeError('audit failure')):
            with self.assertRaises(RuntimeError):
                self.respond('accept_invitation')
        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.status, 'PENDING')
        self.assertFalse(RecruitmentStage.objects.filter(talent=self.talent).exists())

    def test_legacy_talent_routes_use_the_same_safe_response_workflow(self):
        from invitations import views
        for action, callback in (('accept', views.accept_invitation), ('decline', views.decline_invitation)):
            url = f'/talents/invitations/{self.invitation.pk}/{action}/'
            self.assertEqual(resolve(url).func, callback)
            self.assertEqual(self.browser.get(url).status_code, 405)
            self.assertEqual(self.browser.post(url).status_code, 403)

    def test_existing_talent_invite_form_has_a_resolvable_selection_route(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse('invite_talent_profile', args=[self.talent.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="opportunity"')

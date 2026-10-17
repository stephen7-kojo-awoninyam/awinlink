from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from connections.models import Connection, Follow
from talents.models import TalentProfile


class ProfileConnectionTests(TestCase):
    def setUp(self):
        self.viewer = get_user_model().objects.create_user(username='profile-viewer')
        self.target = get_user_model().objects.create_user(username='profile-target')
        self.profile = TalentProfile.objects.create(user=self.target, profile_visibility='PUBLIC')
        self.url = reverse('talent_profile', args=[self.profile.id])
        self.client.force_login(self.viewer)

    def test_connect_is_immediately_after_follow_and_works_when_following(self):
        Follow.objects.create(follower=self.viewer, following=self.target)
        response = self.client.get(self.url)
        self.assertContains(response, '>Connect</button>')
        content = response.content.decode().split('talent-profile-actions', 1)[1].split('talent-hero-bottom', 1)[0]
        self.assertLess(content.index('>Unfollow</button>'), content.index('>Connect</button>'))
        response = self.client.post(reverse('connections:send_connection_request', args=[self.target.id]), HTTP_REFERER=self.url, follow=True)
        self.assertContains(response, '>Request sent</button>')
        self.assertTrue(Follow.objects.filter(follower=self.viewer, following=self.target).exists())

    def test_profile_states_in_both_directions(self):
        for sender, receiver, status, label in [
            (self.viewer, self.target, 'PENDING', 'Request sent'),
            (self.target, self.viewer, 'PENDING', 'Request received'),
            (self.viewer, self.target, 'ACCEPTED', 'Connected'),
            (self.target, self.viewer, 'ACCEPTED', 'Connected'),
            (self.viewer, self.target, 'REJECTED', 'Connect'),
        ]:
            with self.subTest(status=status, sender=sender):
                Connection.objects.all().delete()
                Connection.objects.create(sender=sender, receiver=receiver, status=status)
                self.assertContains(self.client.get(self.url), f'>{label}</')

    def test_own_profile_has_no_connect_action(self):
        self.client.force_login(self.target)
        self.assertNotContains(self.client.get(self.url), '>Connect</button>')

    def test_mobile_api_resends_rejected_request_without_duplicate(self):
        connection = Connection.objects.create(sender=self.viewer, receiver=self.target, status='REJECTED')
        client = APIClient()
        client.force_authenticate(self.viewer)
        response = client.post('/api/connections/create/', {'receiver': self.target.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], connection.id)
        self.assertEqual(response.data['status'], 'PENDING')
        self.assertEqual(client.post('/api/connections/create/', {'receiver': self.target.id}).status_code, 400)
        self.assertEqual(Connection.objects.count(), 1)

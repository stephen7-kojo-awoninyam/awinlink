from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User, UserBlock
from events.models import Event
from organizations.models import Organization
from talents.models import TalentProfile
from .models import Post


class LinkedPostPrivacyTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('linked-post-owner', role='ORGANIZATION')
        self.viewer = User.objects.create_user('linked-post-viewer')
        self.org = Organization.objects.create(user=self.owner, name='Linked org')
        now = timezone.now()
        self.event = Event.objects.create(organizer=self.org, title='Secret draft marker', description='Private draft',
            slug='linked-draft', status='DRAFT', start_date=now, end_date=now+timedelta(hours=1), registration_deadline=now)
        self.post = Post.objects.create(author=self.owner, organization=self.org, event=self.event,
                                       caption='Secret draft marker', visibility='PUBLIC')
        self.api = APIClient(); self.api.force_authenticate(self.viewer)

    def test_draft_association_cannot_leak_through_feed_detail_comments_likes_or_web(self):
        for path in (f'/api/feed/posts/{self.post.pk}/', f'/api/feed/posts/{self.post.pk}/comments/',
                     f'/api/feed/posts/{self.post.pk}/likes/'):
            response = self.api.get(path)
            self.assertIn(response.status_code, (403, 404), path)
            self.assertNotIn(self.post.caption.encode(), response.content)
        self.client.force_login(self.viewer)
        response = self.client.get('/home_feed/')
        self.assertNotContains(response, self.post.caption)
        for action in ('like', 'comment', 'save', 'share'):
            self.assertEqual(self.client.post(f'/feed/{action}/{self.post.pk}/', {'text': 'hidden'}).status_code, 404)
        self.assertEqual(Post.objects.filter(pk=self.post.pk).count(), 1)

    def test_published_post_and_organization_owner_keep_access(self):
        self.api.force_authenticate(self.owner)
        self.assertEqual(self.api.get(f'/api/feed/posts/{self.post.pk}/').status_code, 200)
        self.event.status = 'PUBLISHED'; self.event.save()
        self.api.force_authenticate(self.viewer)
        self.assertEqual(self.api.get(f'/api/feed/posts/{self.post.pk}/').status_code, 200)

    def test_private_or_blocked_talent_association_is_hidden_without_deleting_post(self):
        athlete = User.objects.create_user('linked-talent-owner')
        talent = TalentProfile.objects.create(user=athlete, profile_visibility='PRIVATE')
        self.post.event = None; self.post.talent = talent; self.post.save()
        self.assertEqual(self.api.get(f'/api/feed/posts/{self.post.pk}/').status_code, 404)
        talent.profile_visibility = 'PUBLIC'; talent.save()
        self.assertEqual(self.api.get(f'/api/feed/posts/{self.post.pk}/').status_code, 200)
        UserBlock.objects.create(user=athlete, blocked_user=self.viewer)
        self.assertEqual(self.api.get(f'/api/feed/posts/{self.post.pk}/').status_code, 404)
        self.assertTrue(Post.objects.filter(pk=self.post.pk).exists())

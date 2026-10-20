from types import SimpleNamespace
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from rest_framework.test import APIClient
from organizations.models import Organization, OrganizationMembership
from talents.models import TalentProfile
from .models import Post
from .permissions import authorize_post_associations


class PostAssociationAuthorizationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username='post-owner', role='ORGANIZATION')
        self.actor = User.objects.create_user(username='post-actor')
        self.organization = Organization.objects.create(user=self.owner, name='Post organization', status='ACTIVE')
        self.client = APIClient()
        self.client.force_authenticate(self.actor)

    def create(self, **fields):
        return self.client.post('/api/feed/posts/create/', {'caption': 'Valid post', **fields}, format='json')

    def test_foreign_organization_and_talent_ids_are_rejected(self):
        talent = TalentProfile.objects.create(user=self.owner)
        self.assertEqual(self.create(organization=self.organization.pk).status_code, 403)
        self.assertEqual(self.create(talent=talent.pk).status_code, 403)
        self.assertFalse(Post.objects.exists())

    def test_owner_and_manager_can_post_but_viewer_and_revoked_member_cannot(self):
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.create(organization=self.organization.pk).status_code, 201)
        member = OrganizationMembership.objects.create(organization=self.organization, user=self.actor, role='MANAGER')
        self.client.force_authenticate(self.actor)
        self.assertEqual(self.create(organization=self.organization.pk).status_code, 201)
        member.role = 'VIEWER'
        member.save()
        self.assertEqual(self.create(organization=self.organization.pk).status_code, 403)
        member.role, member.status = 'MANAGER', 'REMOVED'
        member.save()
        self.assertEqual(self.create(organization=self.organization.pk).status_code, 403)

    def test_revoked_author_cannot_detach_workspace_to_bypass_update(self):
        member = OrganizationMembership.objects.create(organization=self.organization, user=self.actor, role='MANAGER')
        post_id = self.create(organization=self.organization.pk).data['id']
        member.status = 'SUSPENDED'
        member.save()
        response = self.client.patch(f'/api/feed/posts/{post_id}/update/', {'organization': None, 'caption': 'Changed'}, format='json')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.delete(f'/api/feed/posts/{post_id}/delete/').status_code, 403)
        self.assertEqual(Post.objects.get(pk=post_id).caption, 'Valid post')

    def test_personal_post_and_own_talent_are_preserved_and_empty_api_post_is_rejected(self):
        talent = TalentProfile.objects.create(user=self.actor)
        self.assertEqual(self.create(talent=talent.pk).status_code, 201)
        self.assertEqual(self.create().status_code, 201)
        self.assertEqual(self.client.post('/api/feed/posts/create/', {'caption': '  '}, format='json').status_code, 400)

    def test_foreign_event_association_requires_its_organizer_permission(self):
        event = SimpleNamespace(organizer=self.organization, organizer_id=self.organization.pk)
        with self.assertRaises(PermissionDenied):
            authorize_post_associations(self.actor, {'event': event})

    def test_demoted_legacy_owner_cannot_post_through_web_or_api(self):
        OrganizationMembership.objects.create(organization=self.organization, user=self.owner, role='VIEWER')
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.create().status_code, 403)
        self.client.force_login(self.owner)
        from django.urls import reverse
        response = self.client.post(reverse('create_post'), {'caption': 'No permission', 'post_type': 'GENERAL', 'visibility': 'PUBLIC'})
        self.assertEqual(response.status_code, 403)

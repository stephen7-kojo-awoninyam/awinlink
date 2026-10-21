from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APITestCase
from . import classroom_services as services
from .models import ClassroomMembership, ClassroomRole
from .test_classroom_security import ClassroomFixture


class ClassroomUserSearchTests(ClassroomFixture, APITestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.url = f'/api/learning/classrooms/{self.classroom.pk}/users/'
        self.client.force_authenticate(self.creator)
        self.candidate = get_user_model().objects.create_user(
            username='Search.Person', first_name='Public', last_name='Name', email='private@example.invalid')

    def search(self, q='search', purpose='invite', **params):
        return self.client.get(self.url, {'q': q, 'purpose': purpose, **params})

    def test_permissions_and_hidden_classrooms(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.search().status_code, 401)
        for user, status in [(self.learner, 403), (self.cohost, 403), (self.admin, 404)]:
            self.client.force_authenticate(user)
            self.assertEqual(self.search().status_code, status)
        self.client.force_authenticate(self.host)
        self.assertEqual(self.search().status_code, 200)
        self.assertEqual(self.search(purpose='cohost').status_code, 403)
        self.client.force_authenticate(self.creator)
        self.assertEqual(self.search(purpose='cohost').status_code, 200)
        self.creator.is_active = False
        self.creator.save(update_fields=['is_active'])
        self.assertEqual(self.search().status_code, 403)

    def test_username_only_case_insensitive_and_minimal_representation(self):
        response = self.search('sEaRcH.PeR')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['results'], [{'id': self.candidate.pk, 'username': 'Search.Person', 'display_name': 'Public Name'}])
        self.assertEqual(self.search('private@example').data['results'], [])
        self.assertEqual(self.search('Public').data['results'], [])
        self.assertIn('no-store', response['Cache-Control'])

    def test_validation_and_inactive_targets(self):
        for query in ['', ' ', 'x', 'x' * 151]:
            self.assertEqual(self.search(query).status_code, 400)
        self.assertEqual(self.search(purpose='admin').status_code, 400)
        self.assertEqual(self.client.get(self.url, {'q': 'search'}).status_code, 400)
        self.candidate.is_active = False
        self.candidate.save(update_fields=['is_active'])
        self.assertEqual(self.search().data['results'], [])
        self.assertEqual(self.search(purpose='cohost').data['results'], [])

    def test_invite_excludes_existing_and_revoked_members(self):
        self.assertEqual(len(self.search().data['results']), 1)
        member = ClassroomMembership.objects.create(classroom=self.classroom, user=self.candidate)
        self.assertEqual(self.search().data['results'], [])
        member.is_active = False
        member.save(update_fields=['is_active'])
        self.assertEqual(self.search().data['results'], [])
        self.assertEqual(self.search('creator').data['results'], [])
        self.assertEqual(self.search('host').data['results'], [])

    def test_cohost_excludes_active_staff_but_allows_restore(self):
        services.end_session(actor=self.host, session=self.session)
        services.assign_classroom_role(actor=self.creator, classroom=self.classroom, user=self.candidate, role=ClassroomRole.COHOST)
        self.assertEqual(self.search(purpose='cohost').data['results'], [])
        services.remove_classroom_cohost(actor=self.creator, classroom=self.classroom, user=self.candidate)
        self.assertEqual(self.search(purpose='cohost').data['results'][0]['id'], self.candidate.pk)
        self.assertEqual(self.search('host', purpose='cohost').data['results'], [])

    def test_literal_wildcards_quotes_and_unicode_are_safe(self):
        User = get_user_model()
        for name in ['literal%_user', "quoted'user", 'caf\u00e9.user']:
            User.objects.create_user(username=name)
        for query, expected in [('%_', 'literal%_user'), ("quoted'", "quoted'user"), ('caf\u00e9', 'caf\u00e9.user')]:
            response = self.search(query)
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual([row['username'] for row in response.data['results']], [expected])
        self.assertEqual(self.search("%' OR 1=1 --").data['results'], [])

    def test_pagination_is_stable_and_bounded(self):
        User = get_user_model()
        User.objects.bulk_create([User(username=f'page-user-{i:03}') for i in range(25)])
        first = self.search('page-user', page_size=10)
        second = self.search('page-user', page_size=10, page=2)
        self.assertEqual(first.data['count'], 25)
        self.assertEqual(len(first.data['results']), 10)
        self.assertTrue(first.data['next'])
        self.assertEqual(len({row['id'] for row in first.data['results'] + second.data['results']}), 20)
        self.assertEqual(first.data['results'][0]['username'], 'page-user-000')

    def test_search_does_not_authorize_stale_target_writes(self):
        target = self.search().data['results'][0]['id']
        self.candidate.is_active = False
        self.candidate.save(update_fields=['is_active'])
        base = f'/api/learning/classrooms/{self.classroom.pk}/'
        self.assertEqual(self.client.post(base + 'invitations/', {'recipient': target}, format='json').status_code, 403)
        services.end_session(actor=self.host, session=self.session)
        self.assertEqual(self.client.post(base + 'staff/', {'user': target, 'role': 'COHOST'}, format='json').status_code, 403)

    def test_throttled_and_unavailable_classrooms(self):
        with patch('learning.classroom_api_views.ClassroomUserSearchThrottle.rate', '1/min'):
            self.assertEqual(self.search().status_code, 200)
            self.assertEqual(self.search().status_code, 429)
        cache.clear()
        self.classroom.is_active = False
        self.classroom.save(update_fields=['is_active'])
        self.assertEqual(self.search().status_code, 400)

from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from organizations.models import Organization


class PaginationSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.viewer = User.objects.create_user(username='page-viewer', role='ATHLETE')
        cls.other = User.objects.create_user(username='other-viewer', role='ATHLETE')
        Organization.objects.bulk_create([Organization(name=f'Organization {n}', country='Nigeria') for n in range(125)])

    def setUp(self):
        self.client = APIClient(); self.client.force_authenticate(self.viewer)

    def next_path(self, response):
        link = response['Link'].split('>')[0][1:]
        url = urlsplit(link)
        return url.path + '?' + url.query

    def test_default_array_and_explicit_envelope_are_bounded_and_reachable(self):
        response = self.client.get('/api/organizations/')
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, list); self.assertEqual(len(response.data), 50)
        seen = [row['id'] for row in response.data]
        while response.has_header('Link') and 'rel="next"' in response['Link']:
            response = self.client.get(self.next_path(response))
            seen += [row['id'] for row in response.data]
        self.assertEqual(len(seen), 125); self.assertEqual(len(set(seen)), 125)
        response = self.client.get('/api/organizations/?page_format=cursor&page_size=999999')
        self.assertEqual(len(response.data['results']), 100)
        self.assertIsNotNone(response.data['next'])

    def test_cursor_tampering_scope_changes_and_duplicate_parameters_fail(self):
        response = self.client.get('/api/organizations/?page_size=2')
        path = self.next_path(response)
        self.assertEqual(self.client.get(path.replace('cursor=', 'cursor=tampered')).status_code, 404)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(path).status_code, 404)
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.client.get(path + '&search=changed').status_code, 404)
        for query in ('page_size=0', 'page_size=-1', 'page_size=oops', 'page_size=1&page_size=2', 'cursor=x&cursor=y'):
            self.assertEqual(self.client.get('/api/organizations/?' + query).status_code, 400)

    def test_inserts_between_pages_do_not_duplicate_or_skip_existing_rows(self):
        first = self.client.get('/api/organizations/?page_size=100')
        Organization.objects.create(name='Concurrent insertion', country='Nigeria')
        second = self.client.get(self.next_path(first))
        ids = [row['id'] for row in first.data + second.data]
        self.assertEqual(len(ids), 125); self.assertEqual(len(set(ids)), 125)

    def test_page_does_not_count_or_materialize_whole_table(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get('/api/organizations/?page_size=2')
        self.assertEqual(len(response.data), 2)
        sql = ' '.join(query['sql'].upper() for query in queries)
        self.assertIn('LIMIT 3', sql)
        self.assertNotIn('COUNT(*)', sql)

    def test_curriculum_preserves_order_and_can_seek_past_a_thousand_equal_values(self):
        from learning.models import Course, Lesson, LearningCategory
        course = Course.objects.create(creator=self.viewer, category=LearningCategory.objects.first(),
                                       title='Large existing curriculum', status='APPROVED')
        Lesson.objects.bulk_create([Lesson(course=course, title=f'Lesson {n}', order=1) for n in range(1005)])
        expected = list(course.lessons.order_by('order', 'pk').values_list('pk', flat=True))
        response = self.client.get(f'/api/learning/courses/{course.pk}/lessons/?page_size=100')
        seen = []
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        while True:
            self.assertEqual(response.status_code, 200)
            seen += [row['id'] for row in response.data]
            if not response.has_header('Link'): break
            with CaptureQueriesContext(connection) as queries:
                response = self.client.get(self.next_path(response))
            self.assertFalse(any('OFFSET' in query['sql'].upper() for query in queries))
        self.assertEqual(seen, expected)

    def test_visibility_is_rechecked_between_talent_pages(self):
        from talents.models import TalentProfile
        from accounts.models import UserBlock
        User = get_user_model()
        users = [User.objects.create_user(username=f'page-talent-{n}', role='ATHLETE') for n in range(3)]
        profiles = [TalentProfile.objects.create(user=user, profile_visibility='PUBLIC') for user in users]
        response = self.client.get('/api/talents/?page_size=1')
        remaining = profiles[1]
        UserBlock.objects.create(user=remaining.user, blocked_user=self.viewer)
        response = self.client.get(self.next_path(response))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(remaining.pk, [row['id'] for row in response.data])

    def test_search_finds_unloaded_rows_and_follow_state_is_not_limited_to_another_first_page(self):
        from connections.models import OrganizationFollow
        oldest = Organization.objects.order_by('pk').first()
        oldest.name = 'Unloaded academy marker'; oldest.save()
        organizations = list(Organization.objects.order_by('pk')[:65])
        OrganizationFollow.objects.bulk_create([OrganizationFollow(user=self.viewer, organization=org) for org in organizations])
        initial = self.client.get('/api/organizations/')
        self.assertNotIn(oldest.pk, [row['id'] for row in initial.data])
        response = self.client.get('/api/organizations/', {'search': 'Unloaded academy marker'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['id'] for row in response.data], [oldest.pk])
        self.assertTrue(response.data[0]['is_followed'])
        self.client.force_authenticate(self.other)
        self.assertFalse(self.client.get('/api/organizations/', {'search': 'Unloaded academy marker'}).data[0]['is_followed'])
        for query in ({'search': 'x' * 201}, {'search': ' '.join(['word'] * 13)}):
            self.assertEqual(self.client.get('/api/organizations/', query).status_code, 400)

    def test_specialist_directory_preserves_only_viewers_own_saved_relationships(self):
        from coaches.models import CoachProfile, CoachTalentBookmark, CoachTalentFollow
        from scouts.models import ScoutProfile, ScoutTalentBookmark, ScoutTalentFollow
        from talents.models import TalentProfile
        talent = TalentProfile.objects.create(user=self.viewer, profile_visibility='PUBLIC')
        for role, Model, Bookmark, Follow, prefix in (
            ('COACH', CoachProfile, CoachTalentBookmark, CoachTalentFollow, 'coaches'),
            ('SCOUT', ScoutProfile, ScoutTalentBookmark, ScoutTalentFollow, 'scouts'),
        ):
            owner = get_user_model().objects.create_user(username=prefix + '-owner', role=role)
            profile = Model.objects.create(user=owner)
            field = role.lower()
            bookmark = Bookmark.objects.create(**{field: profile}, talent=talent)
            follow = Follow.objects.create(**{field: profile}, talent=talent)
            self.client.force_authenticate(owner)
            response = self.client.get(f'/api/{prefix}/talents/', {'search': self.viewer.username})
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data[0]['specialist_bookmark_id'], bookmark.pk)
            self.assertEqual(response.data[0]['specialist_follow_id'], follow.pk)
            outsider = get_user_model().objects.create_user(username=prefix + '-outsider', role=role)
            Model.objects.create(user=outsider)
            self.client.force_authenticate(outsider)
            row = self.client.get(f'/api/{prefix}/talents/', {'search': self.viewer.username}).data[0]
            self.assertIsNone(row['specialist_bookmark_id']); self.assertIsNone(row['specialist_follow_id'])

    def test_scout_order_uses_verified_first_then_username_across_pages(self):
        from scouts.models import ScoutProfile
        from talents.models import TalentProfile
        scout = get_user_model().objects.create_user(username='ordered-scout', role='SCOUT')
        ScoutProfile.objects.create(user=scout)
        profiles = []
        for name, verified in [('zeta', True), ('alpha', False), ('beta', True), ('delta', False)]:
            user = get_user_model().objects.create_user(username='ordered-' + name, role='ATHLETE')
            profiles.append(TalentProfile.objects.create(user=user, profile_visibility='PUBLIC', verified=verified))
        self.client.force_authenticate(scout)
        response = self.client.get('/api/scouts/talents/?page_size=1&search=ordered-')
        seen = []
        while True:
            self.assertEqual(response.status_code, 200, response.data)
            seen += [row['id'] for row in response.data]
            if not response.has_header('Link'): break
            response = self.client.get(self.next_path(response))
        self.assertEqual(seen, [profile.pk for profile in sorted(profiles, key=lambda item: (not item.verified, item.user.username))])

    def test_competition_standings_keep_rank_and_seek_through_unranked_results(self):
        from competitions.models import Competition, CompetitionParticipant, CompetitionResult
        from talents.models import TalentProfile
        from django.utils import timezone
        owner = get_user_model().objects.create_user(username='standing-owner', role='ORGANIZATION')
        organization = Organization.objects.create(user=owner, name='Standing organization')
        today = timezone.localdate()
        competition = Competition.objects.create(organization=organization, title='Standing', category='SPORTS',
            status='RESULTS', registration_start=today, registration_end=today, competition_start=today, competition_end=today)
        results = []
        for index, position in enumerate((None, 2, 1, None)):
            user = get_user_model().objects.create_user(username=f'standing-talent-{index}', role='ATHLETE')
            participant = CompetitionParticipant.objects.create(competition=competition, talent=TalentProfile.objects.create(user=user))
            results.append(CompetitionResult.objects.create(participant=participant, position=position, award='Achievement'))
        response = self.client.get(f'/api/competitions/{competition.pk}/results/?page_size=1')
        seen = []
        while True:
            self.assertEqual(response.status_code, 200, response.data)
            seen += [row['id'] for row in response.data]
            if not response.has_header('Link'): break
            response = self.client.get(self.next_path(response))
        self.assertEqual(seen, [results[2].pk, results[1].pk, results[0].pk, results[3].pk])

    def test_parent_scoped_registration_lookup_reaches_old_history_and_only_own_records(self):
        from competitions.models import Competition, CompetitionParticipant
        from events.models import Event, EventRegistration
        from talents.models import TalentProfile
        from django.utils import timezone
        talent = TalentProfile.objects.create(user=self.viewer)
        other_talent = TalentProfile.objects.create(user=self.other)
        owner = get_user_model().objects.create_user(username='registration-owner', role='ORGANIZATION')
        organization = Organization.objects.create(user=owner, name='Registration organizer')
        now = timezone.now(); today = timezone.localdate()
        events = Event.objects.bulk_create([Event(organizer=organization, title=f'Event {n}', slug=f'parent-page-{n}',
            status='PUBLISHED', start_date=now, end_date=now, registration_deadline=now) for n in range(60)])
        competitions = Competition.objects.bulk_create([Competition(organization=organization, title=f'Competition {n}',
            category='SPORTS', status='PUBLISHED', registration_start=today, registration_end=today,
            competition_start=today, competition_end=today) for n in range(60)])
        registrations = EventRegistration.objects.bulk_create([EventRegistration(talent=talent, event=event) for event in events])
        participants = CompetitionParticipant.objects.bulk_create([CompetitionParticipant(talent=talent, competition=comp,
            submission='Preserve existing submission') for comp in competitions])
        EventRegistration.objects.create(talent=other_talent, event=events[0])
        CompetitionParticipant.objects.create(talent=other_talent, competition=competitions[0])
        for endpoint, parent, records in (
            ('events/my-registrations/', events, registrations), ('competitions/my/', competitions, participants),
        ):
            parameter = 'event' if endpoint.startswith('events/') else 'competition'
            initial = self.client.get('/api/' + endpoint)
            self.assertNotIn(records[0].pk, [row['id'] for row in initial.data])
            selected = self.client.get('/api/' + endpoint, {parameter: parent[0].pk})
            self.assertEqual(selected.status_code, 200, selected.data)
            self.assertEqual([row['id'] for row in selected.data], [records[0].pk])
            self.assertEqual(self.client.get('/api/' + endpoint, {parameter: 'invalid'}).status_code, 400)
        self.assertEqual(self.client.get('/api/competitions/my/', {'competition': competitions[0].pk}).data[0]['submission'], 'Preserve existing submission')
        events[0].title = 'Unloaded event search marker'; events[0].save(update_fields=['title'])
        competitions[0].title = 'Unloaded competition search marker'; competitions[0].save(update_fields=['title'])
        for endpoint, parent, search in (
            ('events/', events[0], 'Unloaded event search marker'),
            ('competitions/', competitions[0], 'Unloaded competition search marker'),
        ):
            response = self.client.get('/api/' + endpoint, {'search': search})
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual([row['id'] for row in response.data], [parent.pk])

    def test_opportunity_search_and_application_status_reach_beyond_the_loaded_page(self):
        from applications.models import Application
        from domains.models import TalentDomain
        from opportunities.models import Opportunity
        from talents.models import TalentProfile
        talent = TalentProfile.objects.create(user=self.viewer)
        domain, _ = TalentDomain.objects.get_or_create(name='Pagination domain')
        organization = Organization.objects.first()
        opportunities = Opportunity.objects.bulk_create([Opportunity(organization=organization, domain=domain,
            title='Unloaded opportunity marker' if n == 0 else f'Other opportunity {n}', active=True) for n in range(60)])
        applications = Application.objects.bulk_create([Application(talent=talent, opportunity=opportunity) for opportunity in opportunities])
        initial = self.client.get('/api/opportunities/')
        self.assertNotIn(opportunities[0].pk, [row['id'] for row in initial.data])
        self.assertNotIn(applications[0].pk, [row['id'] for row in self.client.get('/api/applications/me/').data])
        response = self.client.get('/api/opportunities/', {'search': 'Unloaded opportunity marker'})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([row['id'] for row in response.data], [opportunities[0].pk])
        self.assertTrue(response.data[0]['has_applied'])
        self.client.force_authenticate(self.other)
        self.assertFalse(self.client.get('/api/opportunities/', {'search': 'Unloaded opportunity marker'}).data[0]['has_applied'])

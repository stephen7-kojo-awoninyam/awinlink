from django.test import override_settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APITestCase
from accounts.models import User, UserBlock
from talents.models import TalentProfile
from domains.models import TalentDomain
from scouts.models import ScoutProfile
from coaches.models import CoachProfile
from organizations.models import Organization, OrganizationMembership
from .models import Listing, Offer, DealMessage


@override_settings(ALLOWED_HOSTS=['testserver'], STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.InMemoryStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class MarketTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.talent = User.objects.create_user(username='market_talent')
        cls.profile = TalentProfile.objects.create(user=cls.talent, country='GH')
        cls.scout = User.objects.create_user(username='market_scout', role='SCOUT')
        ScoutProfile.objects.create(user=cls.scout, verified=True)
        cls.coach = User.objects.create_user(username='market_coach', role='COACH')
        CoachProfile.objects.create(user=cls.coach, verified=True)
        cls.outsider = User.objects.create_user(username='market_admin', role='ADMIN', is_staff=True, is_superuser=True)
        cls.domain = TalentDomain.objects.create(name='Basketball')
        cls.listing = Listing.objects.create(talent=cls.profile, ecosystem='SPORTS', subecosystem=cls.domain,
            title='Basketball player', description='Available for a team', status='PUBLISHED', publication_consented_at=timezone.now())
        cls.org = Organization.objects.create(name='Market club', country='GH', user=cls.outsider)
        cls.member = OrganizationMembership.objects.create(organization=cls.org, user=cls.scout, role='RECRUITER')

    def auth(self, user):
        self.client.force_authenticate(user)

    def offer(self, **kwargs):
        return Offer.objects.create(listing=self.listing, sender=self.scout, terms='Training opportunity', **kwargs)

    def test_invalid_filters_are_client_errors(self):
        self.auth(self.scout)
        for key, value in [('subecosystem', '\u00b2'), ('subecosystem', '9223372036854775808'),
                           ('subecosystem', '-1'), ('subecosystem', 'NaN'),
                           ('ecosystem', 'INVALID'), ('work_type', 'office'),
                           ('experience', 'senior'), ('mine', 'yes'), ('country', 'x' * 101),
                           ('q', '\x00')]:
            with self.subTest(key=key, value=value):
                self.assertEqual(self.client.get('/api/marketplace/listings/', {key: value}).status_code, 400)
        self.assertEqual(self.client.get('/api/marketplace/listings/',
                         dict(ecosystem='', subecosystem='', work_type='', experience='')).status_code, 200)

    def test_message_history_pagination_with_concurrent_insert(self):
        offer = self.offer()
        rows = DealMessage.objects.bulk_create([DealMessage(offer=offer, author=self.scout,
                                                           body=f'Message {i}') for i in range(205)])
        self.auth(self.talent)
        url = f'/api/marketplace/deals/{offer.pk}/'
        first = self.client.get(url).data
        self.assertEqual([m['id'] for m in first['messages']], [m.pk for m in rows[-50:]])
        self.assertTrue(first['permissions']['can_accept'])
        self.assertFalse(first['permissions']['can_withdraw'])
        inserted = self.client.post(url + 'messages/', {'body': 'Newest'}, format='json')
        self.assertEqual(inserted.status_code, 201)
        ids = [m['id'] for m in first['messages']]
        cursor = first['next_before']
        while cursor is not None:
            page = self.client.get(url + 'messages/', {'before': cursor})
            self.assertEqual(page.status_code, 200)
            ids = [m['id'] for m in page.data['messages']] + ids
            cursor = page.data['next_before']
        self.assertEqual(ids, [m.pk for m in rows])
        self.assertEqual(self.client.get(url).data['messages'][-1]['id'], inserted.data['id'])

    def test_message_history_empty_and_invalid_cursor(self):
        offer = self.offer()
        self.auth(self.scout)
        url = f'/api/marketplace/deals/{offer.pk}/'
        self.assertEqual(self.client.get(url + 'messages/').data, {'messages': [], 'next_before': None})
        for value in ['bad', '\u00b2', '0', '-1', '9223372036854775808']:
            for path in [url, url + 'messages/']:
                self.assertEqual(self.client.get(path, {'before': value}).status_code, 400)

    def test_final_rooms_remain_readable_but_cannot_message(self):
        for action, actor in [('ACCEPT', self.talent), ('DECLINE', self.talent), ('WITHDRAW', self.scout)]:
            offer = self.offer()
            url = f'/api/marketplace/deals/{offer.pk}/'
            DealMessage.objects.create(offer=offer, author=self.scout, body='Existing history')
            self.auth(actor)
            self.assertEqual(self.client.post(url, {'action': action, 'consent': True}, format='json').status_code, 200)
            for user in [self.talent, self.scout]:
                self.auth(user)
                room = self.client.get(url)
                self.assertFalse(any(room.data['permissions'].values()))
                self.assertEqual(self.client.get(url + 'messages/').data['messages'][0]['body'], 'Existing history')
                self.assertEqual(self.client.post(url + 'messages/', {'body': 'Forbidden'}, format='json').status_code, 400)
            self.assertEqual(offer.messages.count(), 1)

    def test_history_pagination_preserves_access_controls(self):
        offer = self.offer(organization=self.org)
        url = f'/api/marketplace/deals/{offer.pk}/messages/?before=100'
        self.auth(self.talent)
        self.assertEqual(self.client.post(f'/api/marketplace/deals/{offer.pk}/',
                         {'action': 'ACCEPT', 'consent': True}, format='json').status_code, 200)
        self.auth(self.outsider)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.auth(self.scout)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.member.status = 'SUSPENDED'
        self.member.save()
        self.assertEqual(self.client.get(url).status_code, 403)
        self.auth(self.talent)
        self.assertEqual(self.client.get(url).status_code, 200)
        UserBlock.objects.create(user=self.talent, blocked_user=self.scout)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_authentication(self):
        for path in ['markets/', 'listings/', 'offers/', 'deals/1/', 'deals/1/messages/']:
            self.assertEqual(self.client.get('/api/marketplace/' + path).status_code, 401)

    def test_listing_consent_and_owner(self):
        self.auth(self.talent)
        data = dict(ecosystem='SPORTS', subecosystem=self.domain.pk, title='New listing', description='Skills', status='PUBLISHED')
        self.assertEqual(self.client.post('/api/marketplace/listings/', data).status_code, 400)
        data['consent'] = True
        response = self.client.post('/api/marketplace/listings/', data)
        self.assertEqual(response.status_code, 201)
        self.assertIsNotNone(response.data['publication_consented_at'])
        self.assertEqual(response.data['talent'], self.profile.pk)
        self.auth(self.scout)
        self.assertEqual(self.client.patch(f'/api/marketplace/listings/{self.listing.pk}/', {'status': 'PAUSED'}).status_code, 403)

    def test_search_and_privacy(self):
        self.auth(self.scout)
        url = '/api/marketplace/listings/'
        self.assertEqual(self.client.get(url, {'q': 'basketball', 'country': 'gh', 'ecosystem': 'SPORTS', 'subecosystem': self.domain.pk}).data['count'], 1)
        self.assertEqual(self.client.get(url, {'ecosystem': 'ARTS'}).data['count'], 0)
        self.assertEqual(self.client.get(url, {'subecosystem': 'bad'}).status_code, 400)
        for visibility in ['PRIVATE', 'ORGANIZATIONS']:
            self.profile.profile_visibility = visibility
            self.profile.save()
            self.assertEqual(self.client.get(url).data['count'], 0)
            self.assertEqual(self.client.get(f'{url}{self.listing.pk}/').status_code, 404)
        self.auth(self.talent)
        self.assertEqual(self.client.get(url, {'mine': '1'}).data['count'], 1)

    def test_offer_authorization(self):
        url = '/api/marketplace/offers/'
        data = {'listing': self.listing.pk, 'terms': 'Join our team'}
        for user, expected in [(self.talent, 400), (self.outsider, 403), (self.scout, 201), (self.coach, 201)]:
            self.auth(user)
            self.assertEqual(self.client.post(url, data).status_code, expected)
        self.auth(self.scout)
        ScoutProfile.objects.filter(user=self.scout).update(verified=False)
        self.assertEqual(self.client.post(url, data).status_code, 403)
        data['organization'] = self.org.pk
        self.assertEqual(self.client.post(url, data).status_code, 201)
        for status, role in [('ACTIVE', 'VIEWER'), ('SUSPENDED', 'RECRUITER'), ('REMOVED', 'OWNER')]:
            OrganizationMembership.objects.filter(pk=self.member.pk).update(status=status, role=role)
            self.assertEqual(self.client.post(url, data).status_code, 403)

    def test_deal_consent_and_immutable_decision(self):
        offer = self.offer()
        url = f'/api/marketplace/deals/{offer.pk}/'
        self.auth(self.scout)
        self.assertEqual(self.client.post(url, {'action': 'ACCEPT', 'consent': True}).status_code, 403)
        self.auth(self.talent)
        self.assertEqual(self.client.post(url, {'action': 'ACCEPT'}).status_code, 400)
        self.assertEqual(self.client.post(url, {'action': 'ACCEPT', 'consent': 'false'}).status_code, 400)
        self.assertEqual(self.client.post(url, {'action': 'ACCEPT', 'consent': True}).status_code, 200)
        offer.refresh_from_db()
        self.assertEqual(offer.status, 'ACCEPTED')
        self.assertIsNotNone(offer.talent_consented_at)
        self.assertEqual(self.client.post(url, {'action': 'DECLINE'}).status_code, 400)
        self.assertEqual(self.client.post(url + 'messages/', {'body': 'late'}).status_code, 400)

    def test_private_room_and_current_permissions(self):
        offer = self.offer(organization=self.org)
        url = f'/api/marketplace/deals/{offer.pk}/'
        self.auth(self.outsider)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.auth(self.scout)
        self.assertEqual(self.client.post(url + 'messages/', {'body': 'Hello', 'author': self.outsider.pk}).status_code, 201)
        self.assertEqual(offer.messages.get().author_id, self.scout.pk)
        self.member.status = 'SUSPENDED'
        self.member.save()
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.get('/api/marketplace/offers/').data['count'], 0)
        self.auth(self.talent)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_blocking_and_disabled_accounts(self):
        offer = self.offer()
        self.auth(self.scout)
        UserBlock.objects.create(user=self.talent, blocked_user=self.scout)
        self.assertEqual(self.client.get('/api/marketplace/listings/').data['count'], 0)
        self.assertEqual(self.client.get(f'/api/marketplace/deals/{offer.pk}/').status_code, 403)
        User.objects.filter(pk=self.scout.pk).update(is_active=False)
        self.assertEqual(self.client.get('/api/marketplace/listings/').status_code, 403)

    def test_decline_withdraw_and_web(self):
        for user, action in [(self.talent, 'DECLINE'), (self.scout, 'WITHDRAW')]:
            self.auth(user)
            offer = self.offer()
            self.assertEqual(self.client.post(f'/api/marketplace/deals/{offer.pk}/', {'action': action}).status_code, 200)
            offer.refresh_from_db()
            self.assertIsNone(offer.talent_consented_at)
        self.client.force_login(self.talent)
        self.assertContains(self.client.get('/marketplace/'), 'Talent Market')

    def test_duplicate_offers_and_retry_after_withdrawal(self):
        self.auth(self.scout)
        data = {'listing': self.listing.pk, 'terms': 'Exact terms'}
        url = '/api/marketplace/offers/'
        first = self.client.post(url, data)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(self.client.post(url, data).status_code, 400)
        self.assertEqual(Offer.objects.count(), 1)
        self.assertEqual(self.client.post(f'/api/marketplace/deals/{first.data["id"]}/', {'action': 'WITHDRAW'}).status_code, 200)
        self.assertEqual(self.client.post(url, data).status_code, 201)
        data['organization'] = self.org.pk
        self.assertEqual(self.client.post(url, data).status_code, 201)
        OrganizationMembership.objects.create(organization=self.org, user=self.coach, role='RECRUITER')
        self.auth(self.coach)
        self.assertEqual(self.client.post(url, data).status_code, 400)

    def test_hidden_listings_cannot_receive_offers(self):
        self.auth(self.scout)
        for status in ['DRAFT', 'PAUSED']:
            Listing.objects.filter(pk=self.listing.pk).update(status=status)
            self.assertEqual(self.client.post('/api/marketplace/offers/', {'listing': self.listing.pk, 'terms': 'Terms'}).status_code, 404)
        Listing.objects.filter(pk=self.listing.pk).update(status='PUBLISHED')
        User.objects.filter(pk=self.talent.pk).update(is_active=False)
        self.assertEqual(self.client.post('/api/marketplace/offers/', {'listing': self.listing.pk, 'terms': 'Terms'}).status_code, 404)

    def test_forged_fields_and_listing_consent(self):
        self.auth(self.talent)
        url = f'/api/marketplace/listings/{self.listing.pk}/'
        self.assertEqual(self.client.patch(url, {'title': 'Changed'}).status_code, 400)
        self.assertEqual(self.client.patch(url, {'status': 'ACCEPTED', 'consent': True}).status_code, 400)
        self.assertEqual(self.client.patch(url, {'title': 'Changed', 'consent': True, 'talent': 999}).status_code, 200)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.talent_id, self.profile.pk)
        self.auth(self.scout)
        response = self.client.post('/api/marketplace/offers/', {'listing': self.listing.pk, 'terms': 'Terms', 'sender': self.outsider.pk, 'status': 'ACCEPTED', 'talent_consented_at': timezone.now().isoformat()})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['sender'], self.scout.pk)
        self.assertEqual(response.data['status'], 'PENDING')
        self.assertIsNone(response.data['talent_consented_at'])

    def test_room_permissions_cover_every_operation(self):
        offer = self.offer(organization=self.org)
        url = f'/api/marketplace/deals/{offer.pk}/'
        for user in [self.outsider, self.coach]:
            self.auth(user)
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url, {'action': 'ACCEPT', 'consent': True}).status_code, 403)
            self.assertEqual(self.client.post(url + 'messages/', {'body': 'Intrusion'}).status_code, 403)
            self.assertEqual(self.client.get('/api/marketplace/offers/').data['count'], 0)
        self.auth(self.scout)
        for status, role in [('ACTIVE', 'VIEWER'), ('SUSPENDED', 'RECRUITER'), ('REMOVED', 'OWNER')]:
            OrganizationMembership.objects.filter(pk=self.member.pk).update(status=status, role=role)
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url, {'action': 'WITHDRAW'}).status_code, 403)
            self.assertEqual(self.client.post(url + 'messages/', {'body': 'Revoked'}).status_code, 403)
        self.assertFalse(offer.messages.exists())
        offer.refresh_from_db()
        self.assertEqual(offer.status, 'PENDING')

    def test_invalid_actions_and_immutable_terms(self):
        offer = self.offer()
        url = f'/api/marketplace/deals/{offer.pk}/'
        self.auth(self.talent)
        for payload, expected in [({'action': 'WITHDRAW'}, 403), ({'action': 'PENDING'}, 400), ({'status': 'ACCEPTED'}, 400)]:
            self.assertEqual(self.client.post(url, payload).status_code, expected)
        self.assertEqual(self.client.patch(url, {'terms': 'Rewritten'}).status_code, 405)
        self.auth(self.scout)
        self.assertEqual(self.client.post(url, {'action': 'DECLINE'}).status_code, 403)
        self.assertEqual(self.client.post(url + 'messages/', {'body': '   '}).status_code, 400)
        self.assertEqual(self.client.post(url, {'action': 'WITHDRAW'}).status_code, 200)
        self.assertEqual(self.client.post(url, {'action': 'WITHDRAW'}).status_code, 400)
        offer.refresh_from_db()
        self.assertEqual(offer.terms, 'Training opportunity')

    def test_database_guards_for_duplicates_and_consent(self):
        offer = self.offer()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.offer()
        for values in [
            {'status': 'UNKNOWN'},
            {'status': 'ACCEPTED', 'decided_at': timezone.now()},
            {'status': 'PENDING', 'talent_consented_at': timezone.now()},
        ]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                Offer.objects.filter(pk=offer.pk).update(**values)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Listing.objects.filter(pk=self.listing.pk).update(publication_consented_at=None)

    def test_inactive_organization_revokes_sender(self):
        offer = self.offer(organization=self.org)
        Organization.objects.filter(pk=self.org.pk).update(status='INACTIVE')
        self.auth(self.scout)
        self.assertEqual(self.client.get(f'/api/marketplace/deals/{offer.pk}/').status_code, 403)
        self.assertEqual(self.client.post('/api/marketplace/offers/', {'listing': self.listing.pk, 'organization': self.org.pk, 'terms': 'Terms'}).status_code, 403)

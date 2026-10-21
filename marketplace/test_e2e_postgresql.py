"""Real loopback HTTP + JWT workflows against Django's isolated PostgreSQL test DB."""
import json
import os
from pathlib import Path
import subprocess
from unittest import skipUnless
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

from django.core.cache import cache
from django.db import connection
from django.test import Client, override_settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase

from accounts.models import UserBlock
from organizations.models import OrganizationMembership
from scouts.models import ScoutProfile
from .models import DealMessage, Listing, Offer
from . import tests as fixtures


@skipUnless(connection.vendor == 'postgresql', 'Real HTTP PostgreSQL workflows')
@override_settings(ALLOWED_HOSTS=['localhost', '127.0.0.1', 'testserver'], SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False,
    AUTH_RATE_LIMIT_CACHE_ALIAS='default', AUTH_RATE_LIMIT_REQUIRE_SHARED_CACHE=False,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
    STORAGES=fixtures.MarketTests._overridden_settings['STORAGES'])
class MarketHTTPEndToEndTests(StaticLiveServerTestCase):
    setUpTestData = classmethod(fixtures.MarketTests.setUpTestData.__func__)

    def setUp(self):
        self.setUpTestData()
        cache.clear()
        self.tokens = {}
        self.http = build_opener(ProxyHandler({}))
        for user in [self.talent, self.scout, self.coach, self.outsider]:
            user.set_password('LocalMarketAudit123!')
            user.save(update_fields=['password'])
            data = self.request('/api/auth/login/', data={'username': user.username, 'password': 'LocalMarketAudit123!'}, expected=200)
            self.tokens[user.pk] = data['access']

    def request(self, path, user=None, data=None, method=None, expected=200):
        headers = {'Content-Type': 'application/json'}
        if user:
            headers['Authorization'] = 'Bearer ' + self.tokens[user.pk]
        request = Request(self.live_server_url + path, headers=headers,
                          data=json.dumps(data, ensure_ascii=False).encode('utf-8') if data is not None else None,
                          method=method or ('POST' if data is not None else 'GET'))
        try:
            response = self.http.open(request, timeout=60)
        except HTTPError as error:
            response = error
        with response:
            body = json.loads(response.read())
            self.assertEqual(response.status, expected, f'{request.method} {path}: {body}')
            return body

    @skipUnless(os.environ.get('TALENT_MARKET_TEST_CHROME'), 'Set TALENT_MARKET_TEST_CHROME for real browser controls')
    def test_browser_controls_with_real_postgresql_and_session_csrf(self):
        self.run_browser(False)

    @skipUnless(os.environ.get('TALENT_MARKET_TEST_CHROME'), 'Set TALENT_MARKET_TEST_CHROME for real Phase 2 browser controls')
    def test_phase_two_browser_pricing_availability_booking_and_fulfillment_chat(self):
        self.run_browser(True)

    def run_browser(self, phase_two):
        from django.conf import settings
        sessions = {}
        for kind in ['talent', 'scout', 'outsider']:
            client = Client()
            user = getattr(self, kind)
            self.assertTrue(client.login(username=user.username, password='LocalMarketAudit123!'))
            sessions[kind] = client.cookies[settings.SESSION_COOKIE_NAME].value
        fixture = {'origin': self.live_server_url, 'sessions': sessions,
                   'cookie_name': settings.SESSION_COOKIE_NAME, 'domain_id': self.domain.pk, 'phase_two': phase_two}
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(['node', str(root / 'scripts/talent_market_browser_e2e.cjs')],
            input=json.dumps(fixture), capture_output=True, text=True, timeout=240, cwd=root,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['passed'])

    def test_listing_offer_message_acceptance_and_permissions_over_http(self):
        base = '/api/marketplace/'
        self.request(base + 'listings/', expected=401)
        listing_data = {'title': 'Caf\u00e9 talent \U0001f3c0', 'description': 'Available for training',
                        'ecosystem': 'SPORTS', 'subecosystem': self.domain.pk, 'status': 'DRAFT'}
        listing = self.request(base + 'listings/', self.talent, listing_data, expected=201)
        path = base + f'listings/{listing["id"]}/'
        self.request(path, self.scout, expected=404)
        self.request(path, self.talent, {'status': 'PUBLISHED'}, method='PATCH', expected=400)
        self.request(path, self.talent, {'status': 'PUBLISHED', 'consent': True}, method='PATCH')
        found = self.request(base + 'listings/?q=Caf%C3%A9&country=gh', self.scout)
        self.assertEqual(found['results'][0]['title'], listing_data['title'])
        self.request(base + 'listings/?subecosystem=%C2%B2', self.scout, expected=400)
        self.request(path, self.scout, {'title': 'Stolen', 'consent': True}, method='PATCH', expected=403)
        self.request(base + 'offers/', self.outsider, {'listing': listing['id'], 'terms': 'Unverified'}, expected=403)
        offer = self.request(base + 'offers/', self.scout, {'listing': listing['id'], 'terms': 'Exact terms'}, expected=201)
        self.request(base + 'offers/', self.scout, {'listing': listing['id'], 'terms': 'Duplicate'}, expected=400)
        room = base + f'deals/{offer["id"]}/'
        self.request(room, self.outsider, expected=403)
        self.request(room + 'messages/', self.coach, {'body': 'Intrusion'}, expected=403)
        self.request(room, self.scout, {'action': 'ACCEPT', 'consent': True}, expected=403)
        self.request(room, self.talent, {'action': 'ACCEPT'}, expected=400)
        sent = self.request(room + 'messages/', self.scout, {'body': 'Hello \U0001f44b', 'author': self.outsider.pk}, expected=201)
        self.assertEqual(sent['author'], self.scout.pk)
        self.request(room + 'messages/', self.talent, {'body': 'Agreed \u2713'}, expected=201)
        DealMessage.objects.bulk_create([DealMessage(offer_id=offer['id'], author=self.scout, body=f'History {i}') for i in range(51)])
        latest = self.request(room, self.talent)
        self.assertEqual(len(latest['messages']), 50)
        older = self.request(room + f'messages/?before={latest["next_before"]}', self.scout)
        self.assertEqual(len(older['messages']), 3)
        self.assertEqual(older['messages'][0]['body'], 'Hello \U0001f44b')
        accepted = self.request(room, self.talent, {'action': 'ACCEPT', 'consent': True})
        self.assertEqual(accepted['status'], 'ACCEPTED')
        self.assertIsNotNone(accepted['talent_consented_at'])
        for user in [self.scout, self.talent]:
            self.assertFalse(any(self.request(room, user)['permissions'].values()))
            self.request(room + 'messages/', user, {'body': 'After acceptance'}, expected=400)
        self.request(room, self.scout, {'action': 'WITHDRAW'}, expected=400)
        ScoutProfile.objects.filter(user=self.scout).update(verified=False)
        self.request(room, self.scout, expected=403)
        self.request(room, self.talent)
        UserBlock.objects.create(user=self.talent, blocked_user=self.scout)
        self.request(room + 'messages/', self.talent, expected=403)
        self.assertEqual(Offer.objects.get(pk=offer['id']).status, 'ACCEPTED')
        self.assertEqual(DealMessage.objects.filter(offer_id=offer['id']).count(), 53)
        self.assertEqual(Listing.objects.get(pk=listing['id']).title, listing_data['title'])

    def test_organization_sender_revocation_and_final_alternatives_over_http(self):
        base = '/api/marketplace/'
        payload = {'listing': self.listing.pk, 'organization': self.org.pk, 'terms': 'Organization terms'}
        offer = self.request(base + 'offers/', self.scout, payload, expected=201)
        room = base + f'deals/{offer["id"]}/'
        self.request(room, self.outsider, expected=403)
        OrganizationMembership.objects.create(organization=self.org, user=self.coach, role='RECRUITER')
        self.request(room, self.coach, expected=403)
        self.request(base + 'offers/', self.coach, payload, expected=400)
        OrganizationMembership.objects.filter(pk=self.member.pk).update(status='SUSPENDED')
        self.request(room, self.scout, expected=403)
        self.request(room + 'messages/', self.scout, {'body': 'Revoked'}, expected=403)
        self.request(room, self.talent, {'action': 'DECLINE'})
        self.request(room + 'messages/', self.talent, {'body': 'Final'}, expected=400)
        next_offer = self.request(base + 'offers/', self.coach, payload, expected=201)
        next_room = base + f'deals/{next_offer["id"]}/'
        self.request(next_room, self.coach, {'action': 'WITHDRAW'})
        self.request(next_room + 'messages/', self.coach, {'body': 'Final'}, expected=400)

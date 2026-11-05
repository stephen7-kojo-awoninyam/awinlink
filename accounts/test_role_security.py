"""Public account flows must never provision or overwrite administrator authority."""
from datetime import timedelta

from django.contrib.auth.models import Group, Permission
from django.core.cache import cache
from django.test import Client, RequestFactory, TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.forms import UserRegistrationForm
from accounts.google_auth import GoogleSignupForm, digest
from accounts.legal import TERMS_VERSION
from accounts.models import GoogleAuthAttempt, GoogleIdentity, User
from accounts.roles import AUTHORITY_FIELDS, PUBLIC_ROLES
from accounts.tokens import AccountRefreshToken
from talents.models import TalentProfile


@override_settings(AUTH_RATE_LIMIT_CACHE_ALIAS='default', AUTH_RATE_LIMIT_REQUIRE_SHARED_CACHE=False)
class PublicRoleSecurityTests(TestCase):
    password = 'ValidRoleSecurityPassword123!'

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('role-member', password=self.password, role='ATHLETE')
        self.victim = User.objects.create_user('role-victim')
        self.browser = Client(enforce_csrf_checks=True)
        self.browser.force_login(self.user)
        self.browser.get('/onboarding/role/')
        self.api = APIClient()
        self.api.credentials(HTTP_AUTHORIZATION='Bearer ' + str(AccountRefreshToken.for_user(self.user).access_token))

    def post_role(self, role, **extra):
        return self.browser.post('/onboarding/role/', {
            'role': role, 'csrfmiddlewaretoken': self.browser.cookies['csrftoken'].value, **extra,
        })

    def assert_unprivileged(self):
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, 'ATHLETE')
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)
        self.assertFalse(self.user.groups.exists())
        self.assertFalse(self.user.user_permissions.exists())

    def signup(self, **extra):
        return dict(username='new-role-member', email='new-role@example.invalid',
            first_name='Role', last_name='Member', country='GH', phone_number='+233501234567',
            role='ATHLETE', date_of_birth='1990-01-01', password1=self.password, password2=self.password,
            terms_accepted=True, terms_version=TERMS_VERSION, **extra)

    def test_csrf_valid_admin_escalation_is_rejected_and_moderation_remains_denied(self):
        self.assertEqual(self.post_role('ADMIN').status_code, 400)
        self.assert_unprivileged()
        self.assertEqual(self.api.get('/api/role-models/').status_code, 403)
        self.assertEqual(self.api.post('/api/role-models/manual/', {'talent': 1}).status_code, 403)
        self.assertEqual(self.api.post('/api/learning/courses/1/approve/').status_code, 403)
        response = self.browser.post(f'/dashboard/users/toggle/{self.victim.pk}/', {
            'csrfmiddlewaretoken': self.browser.cookies['csrftoken'].value,
        })
        self.assertEqual(response.status_code, 302)
        self.victim.refresh_from_db()
        self.assertTrue(self.victim.is_active)

    def test_onboarding_rejects_unknown_missing_and_altered_admin_values(self):
        for role in ['admin', 'Admin', ' ADMIN', 'ADMIN ', 'SUPERUSER', '', 'ROOT']:
            with self.subTest(role=role):
                self.assertEqual(self.post_role(role).status_code, 400)
                self.assert_unprivileged()
        self.assertEqual(self.browser.post('/onboarding/role/', {
            'csrfmiddlewaretoken': self.browser.cookies['csrftoken'].value,
        }).status_code, 400)
        self.assert_unprivileged()

    def test_onboarding_rejects_privilege_fields_even_with_public_role(self):
        for field in AUTHORITY_FIELDS:
            with self.subTest(field=field):
                self.assertEqual(self.post_role('COACH', **{field: '1'}).status_code, 400)
                self.assert_unprivileged()

    def test_onboarding_requires_session_authentication(self):
        anonymous = Client(enforce_csrf_checks=True)
        self.assertEqual(anonymous.get('/onboarding/role/').status_code, 302)
        self.assert_unprivileged()
        token_only = Client(HTTP_AUTHORIZATION='Bearer ' + str(AccountRefreshToken.for_user(self.user).access_token))
        self.assertEqual(token_only.post('/onboarding/role/', {'role': 'ADMIN'}).status_code, 302)
        self.assert_unprivileged()

    def test_onboarding_preserves_csrf_and_disallows_other_methods(self):
        self.assertEqual(self.browser.post('/onboarding/role/', {'role': 'ADMIN'}).status_code, 403)
        self.assertEqual(self.browser.get('/onboarding/role/?role=ADMIN').status_code, 200)
        self.assertEqual(self.browser.put('/onboarding/role/', {'role': 'ADMIN'}).status_code, 403)
        self.client.force_login(self.user)
        self.assertEqual(self.client.put('/onboarding/role/', {'role': 'ADMIN'}).status_code, 405)
        self.assert_unprivileged()

    def test_public_onboarding_roles_and_legacy_talent_button_still_work(self):
        routes = {'ATHLETE': 'talent_onboarding', 'TALENT': 'talent_onboarding',
            'ORGANIZATION': 'organization_onboarding', 'SCOUT': 'select_scout_category',
            'COACH': 'select_coach_category'}
        for role, route in routes.items():
            with self.subTest(role=role):
                response = self.post_role(role)
                self.assertRedirects(response, reverse(route), fetch_redirect_response=False)
                self.user.refresh_from_db()
                self.assertEqual(self.user.role, 'ATHLETE' if role == 'TALENT' else role)
                self.assertFalse(self.user.is_staff or self.user.is_superuser)

    def test_current_database_admin_is_preserved_even_with_stale_request_user(self):
        from onboarding.views import choose_role
        request = RequestFactory().post('/onboarding/role/', {'role': 'COACH'})
        request.user = self.user
        User.objects.filter(pk=self.user.pk).update(role='ADMIN')
        self.assertEqual(choose_role(request).status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, 'ADMIN')

    def test_legacy_talent_account_can_complete_public_role_selection(self):
        User.objects.filter(pk=self.user.pk).update(role='TALENT')
        self.assertRedirects(self.post_role('TALENT'), reverse('talent_onboarding'), fetch_redirect_response=False)
        self.assert_unprivileged()

    def test_unknown_existing_role_is_not_silently_reclassified(self):
        User.objects.filter(pk=self.user.pk).update(role='UNRECOGNIZED')
        self.assertEqual(self.post_role('COACH').status_code, 403)
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, 'UNRECOGNIZED')

    def test_registration_form_uses_explicit_public_allowlist(self):
        self.assertEqual({key for key, _ in UserRegistrationForm.PUBLIC_ROLE_CHOICES}, PUBLIC_ROLES)
        self.assertNotIn('ADMIN', PUBLIC_ROLES)
        for role in ['ADMIN', 'admin', ' ADMIN', 'ROOT']:
            with self.subTest(role=role):
                data = self.signup()
                data['role'] = role
                form = UserRegistrationForm(data)
                self.assertFalse(form.is_valid())
                self.assertIn('role', form.errors)

    def test_web_and_api_registration_reject_admin_and_permission_injection(self):
        attacks = [{'role': 'ADMIN'}, {'role': 'admin'}] + [{field: '1'} for field in AUTHORITY_FIELDS]
        for attack in attacks:
            with self.subTest(attack=attack):
                cache.clear()
                data = self.signup()
                data.update(attack)
                web = self.client.post('/accounts/register/', data)
                self.assertEqual(web.status_code, 200)
                self.assertTrue(web.context['form'].errors)
                api = APIClient().post('/api/auth/register/', data, format='json')
                self.assertEqual(api.status_code, 400)
                self.assertNotIn('access', api.data)
                self.assertFalse(User.objects.filter(username=data['username']).exists())

    def test_api_public_registration_preserves_all_supported_roles(self):
        for role in PUBLIC_ROLES:
            with self.subTest(role=role):
                cache.clear()
                data = self.signup()
                data.update(role=role, username='signup-' + role.lower(),
                    organization_name='Role Test Organization', organization_username='role-org-' + role.lower(),
                    organization_email='org@example.invalid')
                response = APIClient().post('/api/auth/register/', data, format='json')
                self.assertEqual(response.status_code, 201, response.data)
                created = User.objects.get(pk=response.data['user']['id'])
                self.assertEqual(created.role, role)
                self.assertFalse(created.is_staff or created.is_superuser)

    def test_web_public_registration_still_works(self):
        response = self.client.post('/accounts/register/', self.signup())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(User.objects.get(username='new-role-member').role, 'ATHLETE')

    def google_attempt(self, *, user=None):
        secret, handoff = 's' * 64, 'h' * 64
        claims = {'sub': 'role-test-subject', 'email': 'google-role@example.invalid'}
        if user:
            GoogleIdentity.objects.create(user=user, subject=claims['sub'])
        attempt = GoogleAuthAttempt.objects.create(state='state-role-test', status='VERIFIED',
            claims=claims, mobile_secret_hash=digest(secret), mobile_handoff_hash=digest(handoff),
            expires_at=timezone.now() + timedelta(minutes=5))
        return attempt, {'exchange_secret': secret, 'handoff': handoff}

    def test_google_signup_form_rejects_admin_and_permission_injection(self):
        for attack in [{'role': 'ADMIN'}] + [{field: '1'} for field in AUTHORITY_FIELDS]:
            with self.subTest(attack=attack):
                data = self.signup()
                data.update(attack)
                form = GoogleSignupForm(data, claims={'email': 'google-role@example.invalid'})
                self.assertFalse(form.is_valid())

    def test_google_mobile_api_cannot_issue_admin_tokens_from_signup(self):
        attempt, body = self.google_attempt()
        for attack in [{'role': 'ADMIN'}, {'is_superuser': True}, {'is_staff': True}]:
            with self.subTest(attack=attack):
                cache.clear()
                data = self.signup()
                data.update(attack)
                response = APIClient().post('/api/auth/google/complete/', {**body, 'signup': data}, format='json')
                self.assertEqual(response.status_code, 400, response.data)
                self.assertNotIn('access', response.data)
                self.assertFalse(GoogleIdentity.objects.exists())
                attempt.refresh_from_db()
                self.assertEqual(attempt.status, 'VERIFIED')

    def test_profile_api_mass_assignment_cannot_change_user_authority(self):
        TalentProfile.objects.create(user=self.user)
        for field, value in {'role': 'ADMIN', 'is_staff': True, 'is_superuser': True,
                             'groups': [1], 'user_permissions': [1], 'user': {'role': 'ADMIN'}}.items():
            with self.subTest(field=field):
                self.assertEqual(self.api.patch('/api/talents/me/', {field: value}, format='json').status_code, 400)
                self.assertEqual(self.api.patch('/api/auth/me/', {field: value}, format='json').status_code, 405)
                self.assert_unprivileged()

    def test_token_claims_and_refresh_input_do_not_grant_admin_authority(self):
        refresh = AccountRefreshToken.for_user(self.user)
        refresh['role'], refresh['is_superuser'] = 'ADMIN', True
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION='Bearer ' + str(refresh.access_token))
        self.assertEqual(api.get('/api/role-models/').status_code, 403)
        response = APIClient().post('/api/auth/refresh/', {'refresh': str(refresh), 'role': 'ADMIN'}, format='json')
        self.assertEqual(response.status_code, 200)
        api.credentials(HTTP_AUTHORIZATION='Bearer ' + response.data['access'])
        self.assertEqual(api.get('/api/role-models/').status_code, 403)
        self.assert_unprivileged()

    def test_organization_profile_api_rejects_authority_assignment(self):
        from organizations.models import Organization
        self.user.role = 'ORGANIZATION'
        self.user.save(update_fields=['role'])
        Organization.objects.create(user=self.user, name='Role security organization', status='ACTIVE')
        response = self.api.patch('/api/organizations/me/', {
            'role': 'ADMIN', 'is_staff': True, 'is_superuser': True,
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, 'ORGANIZATION')
        self.assertFalse(self.user.is_staff or self.user.is_superuser)

    def test_recruiter_profile_apis_cannot_reassign_owner_or_user_authority(self):
        from coaches.models import CoachProfile
        from scouts.models import ScoutProfile
        for role, model, path in [('COACH', CoachProfile, '/api/coaches/profile/update/'),
                                  ('SCOUT', ScoutProfile, '/api/scouts/profile/update/')]:
            with self.subTest(role=role):
                self.user.role = role
                self.user.save(update_fields=['role'])
                profile = model.objects.create(user=self.user)
                response = self.api.patch(path, {'role': 'ADMIN', 'is_superuser': True,
                    'is_staff': True, 'user': self.victim.pk, 'verified': True}, format='json')
                self.assertEqual(response.status_code, 200, response.data)
                profile.refresh_from_db()
                self.user.refresh_from_db()
                self.assertEqual(profile.user_id, self.user.pk)
                self.assertFalse(profile.verified)
                self.assertEqual(self.user.role, role)
                self.assertFalse(self.user.is_staff or self.user.is_superuser)

    def test_existing_role_admin_can_login_and_moderate_without_staff_flags(self):
        admin = User.objects.create_user('legitimate-role-admin', password=self.password, role='ADMIN')
        response = APIClient().post('/api/auth/login/', {'username': admin.username, 'password': self.password})
        self.assertEqual(response.status_code, 200)
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION='Bearer ' + response.data['access'])
        self.assertEqual(api.get('/api/role-models/').status_code, 200)
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(admin)
        # Protected accounts redirect before rendering a role-change form.
        self.assertRedirects(browser.get('/onboarding/role/'), reverse('dashboard'), fetch_redirect_response=False)
        browser.get('/accounts/login/')
        token = browser.cookies['csrftoken'].value
        for role in ['ATHLETE', 'COACH', 'ADMIN']:
            self.assertEqual(browser.post('/onboarding/role/', {'role': role, 'csrfmiddlewaretoken': token}).status_code, 302)
        result = browser.post(f'/dashboard/users/toggle/{self.victim.pk}/', {'csrfmiddlewaretoken': token})
        self.assertEqual(result.status_code, 302)
        self.victim.refresh_from_db()
        self.assertFalse(self.victim.is_active)
        admin.refresh_from_db()
        self.assertEqual(admin.role, 'ADMIN')
        self.assertFalse(admin.is_staff or admin.is_superuser)

    def test_staff_superuser_groups_and_permissions_survive_onboarding(self):
        group = Group.objects.create(name='Legitimate administrators')
        permission = Permission.objects.first()
        for flags in [{'is_staff': True}, {'is_staff': True, 'is_superuser': True}]:
            with self.subTest(flags=flags):
                User.objects.filter(pk=self.user.pk).update(**flags)
                self.user.groups.add(group)
                self.user.user_permissions.add(permission)
                self.assertEqual(self.post_role('COACH').status_code, 302)
                self.user.refresh_from_db()
                self.assertEqual(self.user.role, 'ATHLETE')
                for key, value in flags.items():
                    self.assertEqual(getattr(self.user, key), value)
                self.assertTrue(self.user.groups.filter(pk=group.pk).exists())
                self.assertTrue(self.user.user_permissions.filter(pk=permission.pk).exists())

    def test_google_login_preserves_existing_legitimate_admin(self):
        admin = User.objects.create_user('google-legitimate-admin', role='ADMIN')
        _, body = self.google_attempt(user=admin)
        response = APIClient().post('/api/auth/google/complete/', body, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['user']['role'], 'ADMIN')
        admin.refresh_from_db()
        self.assertEqual(admin.role, 'ADMIN')


class ConcurrentRoleSecurityTests(TransactionTestCase):
    @skipUnlessDBFeature('has_select_for_update')
    def test_onboarding_waits_for_trusted_admin_promotion_and_preserves_it(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        from django.db import close_old_connections, connection, transaction
        from onboarding.views import choose_role

        user = User.objects.create_user('concurrent-role-member', role='ATHLETE')
        attempted = Event()

        def onboard():
            close_old_connections()
            request = RequestFactory().post('/onboarding/role/', {'role': 'COACH'})
            request.user = user  # Deliberately stale before trusted provisioning.

            def observe(execute, sql, params, many, context):
                if 'FOR UPDATE' in sql.upper():
                    attempted.set()
                return execute(sql, params, many, context)

            try:
                with connection.execute_wrapper(observe):
                    return choose_role(request).status_code
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                locked = User.objects.select_for_update().get(pk=user.pk)
                pending = pool.submit(onboard)
                self.assertTrue(attempted.wait(10), 'Onboarding did not attempt to lock the user row.')
                locked.role = 'ADMIN'
                locked.save(update_fields=['role'])
            self.assertEqual(pending.result(timeout=10), 302)
        user.refresh_from_db()
        self.assertEqual(user.role, 'ADMIN')

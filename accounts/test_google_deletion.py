import time
from datetime import date, timedelta
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from .google_auth import begin, digest
from .models import GoogleAuthAttempt, GoogleIdentity, GuardianAuthorization, User
from .test_google_auth import CONFIG
from organizations.models import Organization


@override_settings(**CONFIG)
class GoogleDeletionTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.user = User.objects.create_user(username='google-delete', email='same@example.com', date_of_birth=date(1990, 1, 1))
        GoogleIdentity.objects.create(user=self.user, subject='linked-subject')
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def verified(self, *, user=None, mobile=True, subject='linked-subject', **changes):
        attempt, _, secret = begin(mobile=mobile, reauth_user=user or self.user)
        handoff = 'h' * 43
        attempt.status = 'VERIFIED'
        attempt.claims = {'sub': subject, 'email': 'changed@example.com', 'auth_time': int(time.time())}
        attempt.mobile_handoff_hash = digest(handoff) if mobile else ''
        for name, value in changes.items():
            setattr(attempt, name, value)
        attempt.save()
        return attempt, {'exchange_secret': secret, 'handoff': handoff}

    def delete(self, proof, **extra):
        return self.api.delete('/api/auth/account/', {'google_reauth': proof, 'confirm': True, **extra}, format='json')

    def test_start_requires_authentication_linked_identity_and_available_account(self):
        self.assertEqual(APIClient().post('/api/auth/google/start/', {'purpose': 'DELETE'}, format='json').status_code, 400)
        response = self.api.post('/api/auth/google/start/', {'purpose': 'DELETE'}, format='json')
        self.assertEqual(response.status_code, 200)
        query = parse_qs(urlsplit(response.data['authorization_url']).query)
        self.assertEqual(query['max_age'], ['300'])
        self.assertEqual(query['prompt'], ['select_account'])
        self.assertIn('auth_time', query['claims'][0])
        attempt = GoogleAuthAttempt.objects.get(mobile_secret_hash=digest(response.data['exchange_secret']))
        self.assertEqual(attempt.purpose, 'DELETE')
        self.assertEqual(attempt.reauth_user_id, self.user.pk)
        self.assertIsNone(attempt.link_user_id)
        self.assertLessEqual(attempt.expires_at, timezone.now() + timedelta(minutes=5))
        GoogleIdentity.objects.all().delete()
        self.assertEqual(self.api.post('/api/auth/google/start/', {'purpose': 'DELETE'}, format='json').status_code, 400)

    def test_google_only_account_deletes_without_password_and_old_tokens_stop_working(self):
        from .tokens import AccountRefreshToken
        token = AccountRefreshToken.for_user(self.user)
        _, proof = self.verified()
        self.assertFalse(self.user.has_usable_password())
        response = self.delete(proof)
        self.assertEqual(response.status_code, 204)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertFalse(GoogleIdentity.objects.exists())
        self.assertFalse(GoogleAuthAttempt.objects.exists())
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')
        self.assertEqual(client.get('/api/auth/me/').status_code, 401)

    def test_callback_validates_recent_signed_token_before_handoff(self):
        attempt, _, secret = begin(mobile=True, reauth_user=self.user)
        claims = {'sub': 'linked-subject', 'email': 'same@example.com', 'auth_time': int(time.time())}
        response = Mock()
        response.json.return_value = {'id_token': 'provider-token'}
        with patch('accounts.google_auth.httpx.post', return_value=response), patch('accounts.google_auth.validate_id_token', return_value=claims) as validate:
            callback = self.client.get(reverse('google_callback'), {'state': attempt.state, 'code': 'fresh-code'})
        validate.assert_called_once_with('provider-token', attempt.nonce, recent=True)
        handoff = parse_qs(urlsplit(callback['Location']).query)['handoff'][0]
        self.assertNotIn('access', callback['Location'])
        self.assertEqual(self.delete({'exchange_secret': secret, 'handoff': handoff}).status_code, 204)

    def test_ordinary_login_and_link_proofs_never_authorize_deletion(self):
        for link in (None, self.user):
            attempt, _, secret = begin(mobile=True, link_user=link)
            attempt.status = 'VERIFIED'
            attempt.claims = {'sub': 'linked-subject', 'auth_time': int(time.time())}
            attempt.mobile_handoff_hash = digest('h' * 43)
            attempt.save()
            self.assertEqual(self.delete({'exchange_secret': secret, 'handoff': 'h' * 43}).status_code, 400)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_deletion_proof_cannot_issue_tokens_or_link_an_identity(self):
        attempt, proof = self.verified()
        result = self.api.post('/api/auth/google/complete/', proof, format='json')
        self.assertEqual(result.status_code, 400)
        self.assertNotIn('access', result.data)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, 'VERIFIED')

    def test_wrong_subject_same_email_and_other_account_are_rejected(self):
        other = User.objects.create_user(username='other', email=self.user.email)
        GoogleIdentity.objects.create(user=other, subject='other-subject')
        for subject in ('other-subject', 'unlinked-subject'):
            _, proof = self.verified(subject=subject)
            self.assertEqual(self.delete(proof).status_code, 400)
        _, proof = self.verified(user=other, subject='other-subject')
        self.assertEqual(self.delete(proof).status_code, 400)
        self.assertEqual(User.objects.count(), 2)

    def test_expired_pending_failed_consumed_or_changed_credentials_are_rejected(self):
        for changes in ({'expires_at': timezone.now() - timedelta(seconds=1)}, {'status': 'PENDING'},
                        {'status': 'FAILED'}, {'status': 'CONSUMED'}, {'reauth_auth_hash': 'wrong'}):
            _, proof = self.verified(**changes)
            self.assertEqual(self.delete(proof).status_code, 400)
        _, proof = self.verified()
        self.user.set_password('New-password-123!')
        self.user.save()
        self.assertEqual(self.delete(proof).status_code, 400)

    def test_missing_forged_handoff_recent_auth_and_confirmation_are_rejected(self):
        for proof in ({}, None, [], {'id_token': 'forged'}, {'exchange_secret': 'x' * 43, 'handoff': 'h' * 43}):
            self.assertEqual(self.delete(proof).status_code, 400)
        attempt, proof = self.verified()
        for invalid in ({'exchange_secret': proof['exchange_secret']}, {**proof, 'handoff': 'x' * 43}):
            self.assertEqual(self.delete(invalid).status_code, 400)
        for confirm in (False, 'true', None):
            self.assertEqual(self.delete(proof, confirm=confirm).status_code, 400)
        for value in (None, True, time.time(), int(time.time()) - 301, int(time.time()) + 90):
            from django.core.cache import cache
            cache.clear()
            attempt.claims['auth_time'] = value
            attempt.save()
            self.assertEqual(self.delete(proof).status_code, 400)

    def test_deletion_proof_guessing_is_rate_limited(self):
        statuses = [self.delete({}).status_code for _ in range(35)]
        self.assertIn(429, statuses)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_organization_owner_is_preserved_for_google_and_password(self):
        Organization.objects.create(user=self.user, name='Preserved team')
        _, proof = self.verified()
        self.assertEqual(self.delete(proof).status_code, 409)
        self.user.set_password('Secret123!')
        self.user.save()
        self.assertEqual(self.api.delete('/api/auth/account/', {'password': 'Secret123!'}, format='json').status_code, 409)
        self.assertTrue(Organization.objects.filter(user=self.user).exists())

    def test_password_deletion_still_requires_current_password(self):
        self.user.set_password('Secret123!')
        self.user.save()
        self.assertEqual(self.api.delete('/api/auth/account/', {'password': 'wrong'}, format='json').status_code, 400)
        self.assertEqual(self.api.delete('/api/auth/account/', {'password': 'Secret123!'}, format='json').status_code, 204)

    def approve_child(self):
        guardian = User.objects.create_user(username='guardian', date_of_birth=date(1980, 1, 1))
        reviewer = User.objects.create_user(username='reviewer', is_staff=True, date_of_birth=date(1980, 1, 1))
        self.user.date_of_birth = date(timezone.localdate().year - 10, 1, 1)
        self.user.save()
        return GuardianAuthorization.objects.create(child=self.user, guardian=guardian, verified_by=reviewer,
            nominated_email='guardian@example.com', status='APPROVED', verified_at=timezone.now(),
            consented_at=timezone.now(), consent_version='guardian-v1')

    def test_guardian_revocation_after_google_confirmation_immediately_blocks_deletion(self):
        from .age_policy import revoke_guardian
        authorization = self.approve_child()
        _, proof = self.verified()
        revoke_guardian(actor=authorization.guardian, authorization_id=authorization.pk)
        self.assertEqual(self.delete(proof).status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_guardian_identity_cannot_substitute_for_child_google_identity(self):
        authorization = self.approve_child()
        GoogleIdentity.objects.create(user=authorization.guardian, subject='guardian-subject')
        _, proof = self.verified(subject='guardian-subject')
        self.assertEqual(self.delete(proof).status_code, 400)

    def test_guardian_own_deletion_preserves_child_and_withdraws_authority(self):
        authorization = self.approve_child()
        guardian = authorization.guardian
        GoogleIdentity.objects.create(user=guardian, subject='guardian-subject')
        _, proof = self.verified(user=guardian, subject='guardian-subject')
        self.api.force_authenticate(guardian)
        self.assertEqual(self.delete(proof).status_code, 204)
        self.user.refresh_from_db()
        from .age_policy import age_access_allowed
        self.assertFalse(age_access_allowed(self.user))

    def test_web_callback_cannot_delete_and_confirmation_requires_same_session_and_csrf(self):
        self.client.force_login(self.user)
        result = self.client.post(reverse('google_start'), {'purpose': 'DELETE'})
        self.assertEqual(result.status_code, 302)
        state = self.client.session['google_delete_state']
        attempt = GoogleAuthAttempt.objects.get(state=state)
        attempt.status = 'VERIFIED'
        attempt.claims = {'sub': 'linked-subject', 'auth_time': int(time.time())}
        attempt.save()
        with patch('accounts.google_views.exchange', return_value=attempt):
            self.assertEqual(Client().get(reverse('google_callback'), {'state': state, 'code': 'code'}).status_code, 400)
            callback = self.client.get(reverse('google_callback'), {'state': state, 'code': 'code'})
        self.assertRedirects(callback, '/delete-account/', fetch_redirect_response=False)
        self.assertNotIn('google_verified', self.client.session)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertContains(self.client.get('/delete-account/'), 'Permanently delete after Google confirmation')
        csrf = Client(enforce_csrf_checks=True)
        csrf.cookies = self.client.cookies
        self.assertEqual(csrf.post('/delete-account/', {'auth_method': 'google', 'confirm': 'yes'}).status_code, 403)
        self.assertEqual(self.client.post('/delete-account/', {'auth_method': 'google'}).status_code, 400)
        self.assertContains(self.client.post('/delete-account/', {'auth_method': 'google', 'confirm': 'yes'}), 'has been deleted')
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())

    def test_mobile_proof_cannot_be_reused_by_browser(self):
        attempt, _ = self.verified()
        self.client.force_login(self.user)
        session = self.client.session
        session['google_delete_verified'] = attempt.state
        session.save()
        self.assertEqual(self.client.post('/delete-account/', {'auth_method': 'google', 'confirm': 'yes'}).status_code, 400)

    def test_external_google_signin_returns_to_deletion_without_deleting(self):
        self.client.post(reverse('google_start'), {'next': '/delete-account/'})
        state = self.client.session['google_state']
        attempt = GoogleAuthAttempt.objects.get(state=state)
        attempt.status = 'VERIFIED'
        attempt.claims = {'sub': 'linked-subject', 'email': 'same@example.com'}
        attempt.save()
        with patch('accounts.google_views.exchange', return_value=attempt):
            self.client.get(reverse('google_callback'), {'state': state, 'code': 'code'})
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertRedirects(self.client.post(reverse('google_complete')), '/delete-account/')
        self.assertNotIn('google_delete_verified', self.client.session)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_browser_google_deletion_preserves_organization_owner(self):
        Organization.objects.create(user=self.user, name='Preserved browser team')
        self.client.force_login(self.user)
        attempt, _ = self.verified(mobile=False)
        session = self.client.session
        session['google_delete_verified'] = attempt.state
        session.save()
        self.assertContains(self.client.post('/delete-account/', {'auth_method': 'google', 'confirm': 'yes'}),
                            'Transfer organization ownership', status_code=400)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_unlinked_or_inactive_account_invalidates_verified_google_proof(self):
        _, proof = self.verified()
        GoogleIdentity.objects.filter(user=self.user).delete()
        self.assertEqual(self.delete(proof).status_code, 400)
        GoogleIdentity.objects.create(user=self.user, subject='linked-subject')
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.delete(proof).status_code, 403)

    def test_provider_failure_or_cancellation_never_authorizes_deletion(self):
        from .google_auth import GoogleAuthError
        for denied in (False, True):
            attempt, _, secret = begin(mobile=True, reauth_user=self.user)
            response = Mock()
            response.json.return_value = {'id_token': 'invalid-token'}
            with patch('accounts.google_auth.httpx.post', return_value=response) as post, patch('accounts.google_auth.validate_id_token', side_effect=GoogleAuthError('invalid')) as validate:
                callback = self.client.get(reverse('google_callback'), {'state': attempt.state,
                    **({'error': 'access_denied'} if denied else {'code': 'invalid-code'})})
            if denied:
                post.assert_not_called()
                validate.assert_not_called()
            else:
                validate.assert_called_once_with('invalid-token', attempt.nonce, recent=True)
            self.assertIn('error=cancelled', callback['Location'])
            attempt.refresh_from_db()
            self.assertEqual(attempt.status, 'FAILED')
            self.assertEqual(self.delete({'exchange_secret': secret, 'handoff': 'h' * 43}).status_code, 400)

    def test_browser_proof_cannot_be_reused_by_another_account(self):
        attempt, _ = self.verified(mobile=False)
        other = User.objects.create_user(username='another')
        self.client.force_login(other)
        session = self.client.session
        session['google_delete_verified'] = attempt.state
        session.save()
        self.assertEqual(self.client.post('/delete-account/', {'auth_method': 'google', 'confirm': 'yes'}).status_code, 400)
        self.assertEqual(User.objects.count(), 2)

    def test_anonymous_deletion_and_malformed_body_fail_closed(self):
        self.assertEqual(APIClient().delete('/api/auth/account/', {}, format='json').status_code, 401)
        self.assertEqual(self.api.delete('/api/auth/account/', [], format='json').status_code, 400)

    def test_protected_shared_learning_records_return_actionable_conflict_and_roll_back(self):
        from learning.models import Classroom, Course, LearningCategory
        teacher = User.objects.create_user(username='other-course-owner')
        category = LearningCategory.objects.create(name='Shared category')
        course = Course.objects.create(creator=teacher, category=category, title='Shared course', slug='shared-course', description='Shared teaching')
        classroom = Classroom.objects.create(course=course, created_by=self.user, title='Shared classroom')
        attempt, proof = self.verified()
        response = self.delete(proof)
        self.assertEqual(response.status_code, 409)
        self.assertIn('support resolution', response.data['detail'])
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertTrue(Classroom.objects.filter(pk=classroom.pk).exists())
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, 'VERIFIED')
        self.user.set_password('Secret123!')
        self.user.save()
        self.client.force_login(self.user)
        self.assertContains(self.client.post('/delete-account/', {'password': 'Secret123!', 'confirm': 'yes'}),
                            'support resolution', status_code=400)


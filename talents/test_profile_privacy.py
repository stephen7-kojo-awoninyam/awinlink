import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from django.contrib.auth.models import AnonymousUser
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User, UserBlock
from api.serializers import PublicUserSerializer, UserSerializer
from athletes.models import AthleteProfile, AthleteMedia
from athletes.visibility import visible_athlete_profiles_for
from coaches.models import CoachProfile, CoachTalentView, CoachTalentFollow, CoachTalentBookmark
from scouts.models import ScoutProfile, ScoutTalentView, ScoutTalentFollow, ScoutTalentBookmark
from organizations.models import Organization, OrganizationMembership
from talents.models import TalentProfile
from talents.visibility import visible_talent_profiles_for


class ProfilePrivacyTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('private-owner-marker', email='login-secret@example.invalid', role='ATHLETE')
        self.talent = TalentProfile.objects.create(user=self.owner, biography='private biography marker')
        self.coach = User.objects.create_user('coach-viewer', role='COACH'); self.coach_profile = CoachProfile.objects.create(user=self.coach)
        self.scout = User.objects.create_user('scout-viewer', role='SCOUT'); self.scout_profile = ScoutProfile.objects.create(user=self.scout)
        self.api = APIClient()

    def pairs(self):
        return [(self.coach, 'coaches', self.coach_profile, CoachTalentView, CoachTalentFollow, CoachTalentBookmark),
                (self.scout, 'scouts', self.scout_profile, ScoutTalentView, ScoutTalentFollow, ScoutTalentBookmark)]

    def assert_hidden(self, actor, app):
        self.api.force_authenticate(actor)
        response = self.api.get(f'/api/{app}/talents/')
        self.assertEqual(response.status_code, 200); self.assertEqual(response.data, [])
        self.assertIn('no-store', response['Cache-Control'])
        for action in ('view', 'follow', 'bookmark'):
            response = self.api.post(f'/api/{app}/talents/{self.talent.pk}/{action}/', {}, format='json')
            self.assertEqual(response.status_code, 404, (app, action, response.data))

    def test_bidirectional_blocks_cover_api_discovery_and_all_interactions_in_every_category(self):
        for category in ('SPORTS', 'SCIENCE_TECHNOLOGY', 'ARTS', 'OTHERS'):
            self.talent.talent_category = category; self.talent.save()
            for actor, app, profile, views, follows, bookmarks in self.pairs():
                for reverse in (False, True):
                    with self.subTest(category=category, app=app, reverse=reverse):
                        block = UserBlock.objects.create(user=actor if reverse else self.owner,
                            blocked_user=self.owner if reverse else actor)
                        self.assert_hidden(actor, app)
                        self.assertFalse(views.objects.exists()); self.assertFalse(follows.objects.exists()); self.assertFalse(bookmarks.objects.exists())
                        block.delete()

    def test_private_organization_only_and_inactive_targets_cannot_reappear(self):
        for visibility, active in [('PRIVATE', True), ('ORGANIZATIONS', True), ('PUBLIC', False)]:
            self.talent.profile_visibility = visibility; self.talent.save()
            self.owner.is_active = active; self.owner.save()
            for actor, app, *_ in self.pairs():
                self.assert_hidden(actor, app)

    def test_unblocked_public_read_and_interactions_keep_working_without_login_email(self):
        for actor, app, *_ in self.pairs():
            self.api.force_authenticate(actor)
            response = self.api.get(f'/api/{app}/talents/')
            self.assertEqual(response.status_code, 200); self.assertEqual(response.data[0]['id'], self.talent.pk)
            self.assertNotIn('email', response.data[0]['user'])
            self.assertNotIn(self.owner.email, str(response.data))
            for action in ('view', 'follow', 'bookmark'):
                self.assertEqual(self.api.post(f'/api/{app}/talents/{self.talent.pk}/{action}/', {}, format='json').status_code, 201)

    def test_saved_history_is_hidden_without_deleting_relationships_and_safe_removal_still_works(self):
        for actor, app, profile, views, follows, bookmarks in self.pairs():
            kwargs = {'coach' if app == 'coaches' else 'scout': profile, 'talent': self.talent}
            views.objects.create(**kwargs); follows.objects.create(**kwargs); bookmark = bookmarks.objects.create(**kwargs, notes='private note marker')
            UserBlock.objects.create(user=self.owner, blocked_user=actor)
            self.api.force_authenticate(actor)
            for path in ('views', 'following', 'bookmarks'):
                response = self.api.get(f'/api/{app}/talents/{path}/')
                self.assertEqual(response.status_code, 200); self.assertEqual(response.data, [])
            self.assertEqual(self.api.patch(f'/api/{app}/bookmarks/{bookmark.pk}/update/', {'notes': 'changed'}, format='json').status_code, 404)
            bookmark.refresh_from_db(); self.assertEqual(bookmark.notes, 'private note marker')
            self.assertEqual(views.objects.filter(**kwargs).count(), 1); self.assertEqual(follows.objects.filter(**kwargs).count(), 1)
            self.assertEqual(self.api.delete(f'/api/{app}/talents/{self.talent.pk}/unfollow/').status_code, 200)
            self.assertEqual(self.api.delete(f'/api/{app}/bookmarks/{bookmark.pk}/delete/').status_code, 200)

    def test_bookmark_patch_cannot_reassign_to_a_hidden_talent(self):
        hidden_user = User.objects.create_user('hidden-target'); hidden = TalentProfile.objects.create(user=hidden_user, profile_visibility='PRIVATE')
        for actor, app, profile, _, _, bookmarks in self.pairs():
            bookmark = bookmarks.objects.create(**{'coach' if app == 'coaches' else 'scout': profile}, talent=self.talent)
            self.api.force_authenticate(actor)
            response = self.api.patch(f'/api/{app}/bookmarks/{bookmark.pk}/update/', {'talent': hidden.pk, 'notes': 'own note'}, format='json')
            self.assertEqual(response.status_code, 200)
            bookmark.refresh_from_db(); self.assertEqual(bookmark.talent_id, self.talent.pk)

    def test_web_discovery_saved_views_and_mutations_respect_blocks(self):
        for actor, app, profile, views, follows, bookmarks in self.pairs():
            kwargs = {'coach' if app == 'coaches' else 'scout': profile, 'talent': self.talent}
            views.objects.create(**kwargs); follows.objects.create(**kwargs); bookmarks.objects.create(**kwargs)
            UserBlock.objects.create(user=actor, blocked_user=self.owner)
            self.client.force_login(actor)
            paths = [f'/{app}/talents/', f'/{app}/saved-talents/']
            if app == 'scouts': paths += ['/scouts/bookmarks/', '/scouts/following/']
            for path in paths:
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, path)
                self.assertNotContains(response, self.owner.username)
            self.assertEqual(self.client.get(f'/{app}/talents/{self.talent.pk}/').status_code, 404)
            for action in ('follow', 'save' if app == 'coaches' else 'bookmark'):
                self.assertEqual(self.client.post(f'/{app}/talents/{self.talent.pk}/{action}/').status_code, 404)

    def test_self_account_email_remains_separate_from_public_profile_data(self):
        self.api.force_authenticate(self.owner)
        self.assertEqual(self.api.get('/api/auth/me/').data['email'], self.owner.email)
        for path in (f'/api/talents/{self.talent.pk}/', '/api/talents/', '/api/talents/me/'):
            result = self.api.get(path)
            self.assertEqual(result.status_code, 200); self.assertNotIn(self.owner.email, str(result.data))
        self.assertNotIn('email', PublicUserSerializer(self.owner).data)
        self.assertEqual(UserSerializer(self.owner).data['email'], self.owner.email)

    def test_stale_disabled_actor_has_no_canonical_visibility(self):
        User.objects.filter(pk=self.coach.pk).update(is_active=False)
        self.assertFalse(visible_talent_profiles_for(self.coach).exists())

    def test_stale_recruiter_role_cannot_create_interactions(self):
        User.objects.filter(pk=self.coach.pk).update(role='ATHLETE')
        self.api.force_authenticate(self.coach)
        self.assertEqual(self.api.post(f'/api/coaches/talents/{self.talent.pk}/follow/').status_code, 403)
        self.assertFalse(CoachTalentFollow.objects.exists())

    def test_current_org_capability_still_controls_canonical_organization_visibility(self):
        org_user = User.objects.create_user('org-reader', role='ORGANIZATION')
        org = Organization.objects.create(user=org_user, name='Reader org')
        member = OrganizationMembership.objects.create(user=self.coach, organization=org, role='VIEWER')
        self.talent.profile_visibility = 'ORGANIZATIONS'; self.talent.save()
        self.api.force_authenticate(self.coach)
        self.assertEqual(self.api.get(f'/api/talents/{self.talent.pk}/').status_code, 200)
        # Existing recruiter discovery remains public-only.
        self.assertEqual(self.api.get('/api/coaches/talents/').data, [])
        member.status = 'REMOVED'; member.save()
        self.assertEqual(self.api.get(f'/api/talents/{self.talent.pk}/').status_code, 404)


class LegacyAthletePrivacyTests(TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        override = override_settings(MEDIA_ROOT=directory.name, STORAGES={
            'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
        override.enable(); self.addCleanup(override.disable)
        self.owner = User.objects.create_user('legacy-owner', role='ATHLETE')
        self.viewer = User.objects.create_user('legacy-viewer', role='SCOUT')
        self.profile = AthleteProfile.objects.create(user=self.owner, date_of_birth=date(2000, 1, 1), height=180, weight=70, biography='legacy secret marker')
        self.asset = FileSystemStorage().save('athletes/media/legacy.txt', ContentFile(b'original legacy bytes'))
        AthleteMedia.objects.create(athlete=self.profile, title='Work', media_type='IMAGE', file=self.asset)
        self.api = APIClient()

    def assert_access(self, user, status):
        self.api.force_authenticate(user)
        if user is not None: self.client.force_login(user)
        else: self.client.logout()
        response = self.client.get(f'/athletes/{self.profile.pk}/')
        self.assertEqual(response.status_code, status)
        for method in ('get', 'head'):
            result = getattr(self.api, method)('/media/' + self.asset)
            self.assertEqual(result.status_code, status); self.assertIn('no-store', result['Cache-Control']); result.close()

    def test_legacy_only_is_owner_only_and_preserves_content(self):
        self.assert_access(None, 404); self.assert_access(self.viewer, 404); self.assert_access(self.owner, 200)
        self.profile.refresh_from_db(); self.assertEqual(self.profile.biography, 'legacy secret marker')
        self.assertEqual(Path(FileSystemStorage().path(self.asset)).read_bytes(), b'original legacy bytes')

    def test_linked_visibility_blocks_and_account_status_apply_to_page_and_file(self):
        talent = TalentProfile.objects.create(user=self.owner, profile_visibility='PRIVATE')
        self.assert_access(None, 404); self.assert_access(self.viewer, 404); self.assert_access(self.owner, 200)
        talent.profile_visibility = 'PUBLIC'; talent.save()
        self.assert_access(None, 200); self.assert_access(self.viewer, 200)
        for reverse in (False, True):
            block = UserBlock.objects.create(user=self.viewer if reverse else self.owner, blocked_user=self.owner if reverse else self.viewer)
            self.assert_access(self.viewer, 404); block.delete()
        User.objects.filter(pk=self.owner.pk).update(is_active=False)
        self.assert_access(None, 404); self.assert_access(self.owner, 404)

    def test_orphaned_asset_is_denied_without_deleting_bytes(self):
        self.profile.media.all().delete()
        self.api.force_authenticate(self.owner)
        self.assertEqual(self.api.get('/media/' + self.asset).status_code, 404)
        self.assertTrue(FileSystemStorage().exists(self.asset))

    def test_cloud_acl_runs_before_provider_access(self):
        from config.media_views import _media_is_allowed
        self.assertFalse(_media_is_allowed(self.viewer, self.asset))
        with patch('config.media_views.requests.Session') as provider:
            self.assert_access(self.viewer, 404); provider.assert_not_called()

    def test_canonical_photos_achievements_and_certificates_share_visibility_and_blocks(self):
        from talents.models import Achievement, Certification
        talent = TalentProfile.objects.create(user=self.owner, profile_visibility='PRIVATE')
        paths = [FileSystemStorage().save(prefix + 'original.png', ContentFile(b'\x89PNG\r\n\x1a\noriginal bytes'))
                 for prefix in ('talents/profile/', 'talents/cover/', 'achievements/', 'certifications/')]
        talent.profile_photo = paths[0]; talent.cover_photo = paths[1]; talent.save()
        Achievement.objects.create(talent=talent, title='Private achievement', image=paths[2])
        Certification.objects.create(talent=talent, name='Private certificate', issuing_organization='Issuer', issue_date=date(2020, 1, 1), certificate_file=paths[3])
        for user, status in ((None, 404), (self.viewer, 404), (self.owner, 200)):
            self.api.force_authenticate(user)
            for path in paths:
                response = self.api.get('/media/' + path); self.assertEqual(response.status_code, status); response.close()
        talent.profile_visibility = 'PUBLIC'; talent.save()
        self.api.force_authenticate(self.viewer)
        for path in paths:
            response = self.api.get('/media/' + path); self.assertEqual(response.status_code, 200); response.close()
        UserBlock.objects.create(user=self.viewer, blocked_user=self.owner)
        for path in paths:
            self.assertEqual(self.api.get('/media/' + path).status_code, 404)
            self.assertTrue(FileSystemStorage().exists(path))

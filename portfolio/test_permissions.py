"""Portfolio authorization must agree for parent, item, page and asset access."""
import io
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User, UserBlock
from accounts.tokens import AccountRefreshToken
from config.media_storage import PlaybackMediaStorage
from organizations.models import Organization, OrganizationMembership
from talents.models import TalentProfile
from .models import PortfolioItem


@override_settings(STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class PortfolioPermissionTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='awinlink-portfolio-permissions-')
        self.addCleanup(self.directory.cleanup)
        setting = override_settings(MEDIA_ROOT=self.directory.name)
        setting.enable()
        self.addCleanup(setting.disable)
        self.owner = User.objects.create_user('portfolio-owner')
        self.viewer = User.objects.create_user('portfolio-viewer')
        self.talent = TalentProfile.objects.create(user=self.owner, profile_visibility='PRIVATE')
        self.viewer_talent = TalentProfile.objects.create(user=self.viewer)
        self.pdf = b'%PDF-1.7\nprivate portfolio bytes\n%%EOF'
        image = io.BytesIO()
        Image.new('RGB', (2, 2), 'blue').save(image, format='PNG')
        self.png = image.getvalue()
        storage = FileSystemStorage()
        file = storage.save('portfolio/files/work.pdf', ContentFile(self.pdf))
        picture = storage.save('portfolio/images/work.png', ContentFile(self.png))
        self.item = PortfolioItem.objects.create(talent=self.talent, title='Confidential portfolio marker',
            description='Private project description marker', item_type='DOCUMENT', file=file, image=picture,
            link='https://example.invalid/private-project')
        self.api = APIClient()

    def as_user(self, user):
        self.api.force_authenticate(user=user)

    def visibility(self, value):
        self.talent.profile_visibility = value
        self.talent.save(update_fields=['profile_visibility'])

    def assert_read(self, user, status):
        self.as_user(user)
        for path in [f'/api/portfolio/talent/{self.talent.pk}/', f'/api/portfolio/{self.item.pk}/',
                     '/media/' + self.item.file.name, '/media/' + self.item.image.name]:
            with self.subTest(path=path, viewer=getattr(user, 'username', None)):
                response = self.api.get(path)
                self.assertEqual(response.status_code, status)
                self.assertIn('no-store', response['Cache-Control'])
                if status == 404:
                    self.assertNotIn('Confidential portfolio marker', str(getattr(response, 'data', '')))
                response.close()

    def organization(self):
        user = User.objects.create_user('portfolio-org-owner', role='ORGANIZATION')
        return Organization.objects.create(user=user, name='Portfolio Organization', status='ACTIVE')

    def test_private_parent_item_and_assets_deny_all_nonowner_roles(self):
        for role in ['ATHLETE', 'SCOUT', 'COACH', 'ORGANIZATION', 'ADMIN']:
            with self.subTest(role=role):
                self.viewer.role = role
                self.viewer.save(update_fields=['role'])
                self.assert_read(self.viewer, 404)

    def test_private_portfolio_owner_can_read_items_and_original_bytes(self):
        self.assert_read(self.owner, 200)
        self.as_user(self.owner)
        response = self.api.get('/media/' + self.item.file.name)
        self.assertEqual(b''.join(response.streaming_content), self.pdf)
        self.assertTrue(response['Content-Disposition'].startswith('attachment'))
        picture = self.api.get('/media/' + self.item.image.name)
        self.assertEqual(b''.join(picture.streaming_content), self.png)
        self.assertEqual(picture['Content-Type'], 'image/png')

    def test_public_portfolio_all_active_unblocked_roles_can_read(self):
        self.visibility('PUBLIC')
        for role in ['ATHLETE', 'SCOUT', 'COACH', 'ORGANIZATION', 'ADMIN']:
            with self.subTest(role=role):
                self.viewer.role = role
                self.viewer.save(update_fields=['role'])
                self.assert_read(self.viewer, 200)

    def test_public_asset_urls_are_public_but_private_and_organization_assets_are_not(self):
        self.as_user(None)
        for visibility, status in [('PRIVATE', 404), ('ORGANIZATIONS', 404), ('PUBLIC', 200)]:
            self.visibility(visibility)
            response = self.api.get('/media/' + self.item.file.name)
            self.assertEqual(response.status_code, status)
            response.close()
        self.assertEqual(self.api.get(f'/api/portfolio/{self.item.pk}/').status_code, 401)

    def test_staff_and_superuser_flags_do_not_grant_private_portfolio_access(self):
        self.viewer.role = 'ADMIN'; self.viewer.is_staff = True; self.viewer.is_superuser = True
        self.viewer.save(update_fields=['role', 'is_staff', 'is_superuser'])
        self.assert_read(self.viewer, 404)

    def test_organization_role_without_an_active_capability_is_not_enough(self):
        self.visibility('ORGANIZATIONS')
        self.viewer.role = 'ORGANIZATION'; self.viewer.save(update_fields=['role'])
        self.assert_read(self.viewer, 404)
        self.as_user(self.viewer)
        self.assertEqual(self.api.get(f'/api/portfolio/talent/{self.talent.pk}/?organization_id=123').status_code, 404)

    def test_active_organization_owner_can_read_organization_only_portfolio_but_not_private(self):
        organization = self.organization()
        self.visibility('ORGANIZATIONS')
        self.assert_read(organization.user, 200)
        self.visibility('PRIVATE')
        self.assert_read(organization.user, 404)

    def test_membership_capability_applies_across_scout_coach_and_talent_roles(self):
        organization = self.organization()
        self.visibility('ORGANIZATIONS')
        member = OrganizationMembership.objects.create(organization=organization, user=self.viewer, role='VIEWER')
        for role in ['SCOUT', 'COACH', 'ATHLETE']:
            with self.subTest(role=role):
                self.viewer.role = role; self.viewer.save(update_fields=['role'])
                self.assert_read(self.viewer, 200)
        member.status = 'REMOVED'; member.save(update_fields=['status'])
        self.assert_read(self.viewer, 404)

    def test_organization_suspension_and_membership_suspension_are_immediate(self):
        organization = self.organization()
        self.visibility('ORGANIZATIONS')
        member = OrganizationMembership.objects.create(organization=organization, user=self.viewer, role='RECRUITER')
        self.assert_read(self.viewer, 200)
        member.status = 'SUSPENDED'; member.save(update_fields=['status'])
        self.assert_read(self.viewer, 404)
        member.status = 'ACTIVE'; member.save(update_fields=['status'])
        organization.status = 'SUSPENDED'; organization.save(update_fields=['status'])
        self.assert_read(self.viewer, 404)

    def test_organization_read_capability_never_grants_portfolio_ownership(self):
        organization = self.organization()
        self.visibility('ORGANIZATIONS')
        OrganizationMembership.objects.create(organization=organization, user=self.viewer, role='MANAGER')
        self.assert_read(self.viewer, 200)
        self.assertEqual(self.api.patch(f'/api/portfolio/{self.item.pk}/update/', {'title': 'No ownership'}, format='json').status_code, 404)
        self.assertEqual(self.api.delete(f'/api/portfolio/{self.item.pk}/delete/').status_code, 404)
    def test_bidirectional_blocks_override_public_and_organization_access(self):
        organization = self.organization()
        OrganizationMembership.objects.create(organization=organization, user=self.viewer, role='VIEWER')
        for visibility in ['PUBLIC', 'ORGANIZATIONS']:
            self.visibility(visibility)
            for source, target in [(self.owner, self.viewer), (self.viewer, self.owner)]:
                with self.subTest(visibility=visibility, source=source.username):
                    block = UserBlock.objects.create(user=source, blocked_user=target)
                    self.assert_read(self.viewer, 404)
                    block.delete()
                    self.assert_read(self.viewer, 200)

    def test_privacy_rules_apply_to_every_talent_category(self):
        for category in ['SPORTS', 'SCIENCE_TECHNOLOGY', 'ARTS', 'OTHERS']:
            TalentProfile.objects.filter(pk=self.talent.pk).update(talent_category=category, talent_area='Public speaking')
            self.visibility('PRIVATE')
            self.assert_read(self.viewer, 404)
            self.assert_read(self.owner, 200)

    def test_visibility_changes_revoke_previous_item_and_asset_access(self):
        self.visibility('PUBLIC'); self.assert_read(self.viewer, 200)
        self.visibility('PRIVATE'); self.assert_read(self.viewer, 404)
        self.assert_read(self.owner, 200)
        self.assertEqual(Path(self.directory.name, self.item.file.name).read_bytes(), self.pdf)

    def test_inactive_source_and_stale_inactive_viewer_are_denied(self):
        self.visibility('PUBLIC')
        User.objects.filter(pk=self.owner.pk).update(is_active=False)
        self.assert_read(self.viewer, 404)
        User.objects.filter(pk=self.owner.pk).update(is_active=True)
        User.objects.filter(pk=self.viewer.pk).update(is_active=False)
        self.as_user(self.viewer)  # Deliberately stale authenticated object.
        self.assertEqual(self.api.get(f'/api/portfolio/{self.item.pk}/').status_code, 404)
        self.assertEqual(self.api.get('/media/' + self.item.file.name).status_code, 404)

    def test_empty_private_portfolio_does_not_bypass_parent_authorization(self):
        self.item.delete()
        self.as_user(self.viewer)
        self.assertEqual(self.api.get(f'/api/portfolio/talent/{self.talent.pk}/').status_code, 404)
        self.as_user(self.owner)
        self.assertEqual(self.api.get(f'/api/portfolio/talent/{self.talent.pk}/').data, [])

    def test_another_talent_cannot_edit_or_delete_even_when_the_item_is_public(self):
        self.visibility('PUBLIC'); self.as_user(self.viewer)
        self.assertEqual(self.api.patch(f'/api/portfolio/{self.item.pk}/update/', {'title': 'Stolen'}, format='json').status_code, 404)
        self.assertEqual(self.api.delete(f'/api/portfolio/{self.item.pk}/delete/').status_code, 404)
        from media_erasure.models import MediaErasureJob
        self.assertFalse(MediaErasureJob.objects.exists())
        self.item.refresh_from_db()
        self.assertEqual(self.item.title, 'Confidential portfolio marker')

    def test_viewer_recruiter_or_admin_cannot_manage_another_users_portfolio(self):
        for role in ['SCOUT', 'COACH', 'ORGANIZATION', 'ADMIN']:
            self.viewer.role = role; self.viewer.save(update_fields=['role']); self.as_user(self.viewer)
            for path, method in [('/api/portfolio/create/', 'post'), (f'/api/portfolio/{self.item.pk}/update/', 'patch')]:
                self.assertEqual(getattr(self.api, method)(path, {'title': 'No access', 'item_type': 'PROJECT'}, format='json').status_code, 403)
            self.assertEqual(self.api.delete(f'/api/portfolio/{self.item.pk}/delete/').status_code, 403)

    def test_owner_can_create_edit_and_delete_without_changing_other_portfolios(self):
        self.as_user(self.owner)
        created = self.api.post('/api/portfolio/create/', {'title': 'New work', 'item_type': 'PROJECT'}, format='json')
        self.assertEqual(created.status_code, 201)
        row = PortfolioItem.objects.get(pk=created.data['id'])
        self.assertEqual(row.talent_id, self.talent.pk)
        changed = self.api.patch(f'/api/portfolio/{row.pk}/update/', {'title': 'Updated work'}, format='json')
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(self.api.delete(f'/api/portfolio/{row.pk}/delete/').status_code, 204)
        self.assertTrue(PortfolioItem.objects.filter(pk=self.item.pk).exists())

    def test_owner_delete_revokes_media_access_and_retains_bytes_for_retention_policy(self):
        from media_erasure.models import MediaErasureJob
        self.visibility('PUBLIC')
        file_name, image_name = self.item.file.name, self.item.image.name
        self.as_user(self.viewer)
        before = self.api.get('/media/' + file_name)
        self.assertEqual(before.status_code, 200)
        before.close()
        self.as_user(self.owner)
        self.assertEqual(self.api.delete(f'/api/portfolio/{self.item.pk}/delete/').status_code, 204)
        queued = MediaErasureJob.objects.filter(source_pk=str(self.item.pk), source_model='portfolio.portfolioitem')
        self.assertEqual(queued.count(), 2)
        self.assertTrue(all(job.retain_until >= job.requested_at + timedelta(days=30)
                            for job in queued))
        self.as_user(self.viewer)
        denied_file = self.api.get('/media/' + file_name)
        denied_image = self.api.get('/media/' + image_name)
        self.assertEqual(denied_file.status_code, 404)
        self.assertEqual(denied_image.status_code, 404)
        denied_file.close(); denied_image.close()
        # Deletion revokes the application's reference immediately. Physical
        # erasure remains governed by an explicit retention/hold decision.
        storage = FileSystemStorage()
        self.assertTrue(storage.exists(file_name))
        self.assertTrue(storage.exists(image_name))

    def test_replaced_file_enters_retention_queue_without_deleting_original(self):
        from media_erasure.models import MediaErasureJob
        old_name = self.item.file.name
        self.as_user(self.owner)
        new_pdf = SimpleUploadedFile('replacement.pdf', b'%PDF-1.7\nreplacement\n%%EOF', 'application/pdf')
        result = self.api.patch(f'/api/portfolio/{self.item.pk}/update/', {'file': new_pdf}, format='multipart')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertTrue(MediaErasureJob.objects.filter(storage_name=old_name, source_field='file',
            source_model='portfolio.portfolioitem').exists())
        self.assertTrue(FileSystemStorage().exists(old_name))

    def test_api_and_web_forms_reject_ownership_assignment(self):
        self.as_user(self.owner)
        web = Client(); web.force_login(self.owner)
        for field in ['talent', 'talent_id', 'user', 'user_id', 'owner', 'owner_id']:
            with self.subTest(field=field):
                body = {'title': 'Forged owner', 'item_type': 'PROJECT', field: self.viewer_talent.pk}
                self.assertEqual(self.api.post('/api/portfolio/create/', body, format='json').status_code, 400)
                self.assertEqual(self.api.patch(f'/api/portfolio/{self.item.pk}/update/', body, format='json').status_code, 400)
                response = web.post(f'/portfolio/edit/{self.item.pk}/', body)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['form'].errors)
        self.item.refresh_from_db()
        self.assertEqual(self.item.talent_id, self.talent.pk)
        self.assertEqual(self.item.title, 'Confidential portfolio marker')

    def test_malformed_json_remains_a_validation_error(self):
        self.as_user(self.owner)
        self.assertEqual(self.api.post('/api/portfolio/create/', [{'talent': self.talent.pk}], format='json').status_code, 400)

    def test_web_profile_does_not_render_private_or_blocked_portfolio(self):
        web = Client(); web.force_login(self.viewer)
        path = f'/talents/profile/{self.talent.pk}/'
        self.assertEqual(web.get(path).status_code, 404)
        self.visibility('PUBLIC')
        self.assertContains(web.get(path), self.item.title)
        UserBlock.objects.create(user=self.owner, blocked_user=self.viewer)
        self.assertEqual(web.get(path).status_code, 404)

    def test_web_management_is_owner_only_and_still_uses_csrf(self):
        web = Client(enforce_csrf_checks=True); web.force_login(self.owner)
        self.assertEqual(web.get('/portfolio/').status_code, 200)
        self.assertEqual(web.post(f'/portfolio/delete/{self.item.pk}/').status_code, 403)
        response = web.post(f'/portfolio/edit/{self.item.pk}/', {'title': 'Owner edit', 'item_type': 'DOCUMENT',
            'csrfmiddlewaretoken': web.cookies['csrftoken'].value})
        self.assertEqual(response.status_code, 302)
        self.item.refresh_from_db(); self.assertEqual(self.item.title, 'Owner edit')
        web.force_login(self.viewer)
        self.assertEqual(web.get(f'/portfolio/edit/{self.item.pk}/').status_code, 404)
        self.assertEqual(web.get(f'/portfolio/delete/{self.item.pk}/').status_code, 405)

    def test_web_and_api_use_current_owner_role_not_stale_request_role(self):
        self.as_user(self.owner)
        User.objects.filter(pk=self.owner.pk).update(role='COACH')
        self.assertEqual(self.api.post('/api/portfolio/create/', {'title': 'Nope', 'item_type': 'PROJECT'}, format='json').status_code, 403)
        web = Client(); web.force_login(self.owner)
        self.assertEqual(web.get('/portfolio/add/').status_code, 403)
        self.assertEqual(web.get('/portfolio/').status_code, 403)
        page = web.get(f'/talents/profile/{self.talent.pk}/')
        self.assertContains(page, self.item.title)
        self.assertNotContains(page, 'Manage portfolio')
        self.assertNotContains(page, 'Add work')

    def test_asset_range_and_head_recheck_privacy_and_blocks(self):
        self.visibility('PUBLIC'); self.as_user(self.viewer)
        path = '/media/' + self.item.file.name
        response = self.api.get(path, HTTP_RANGE='bytes=0-5')
        self.assertEqual(response.status_code, 206)
        self.assertEqual(b''.join(response.streaming_content), self.pdf[:6])
        UserBlock.objects.create(user=self.viewer, blocked_user=self.owner)
        self.assertEqual(self.api.head(path).status_code, 404)
        self.assertEqual(self.api.get(path, HTTP_RANGE='bytes=0-5').status_code, 404)

    def test_orphaned_assets_have_no_implicit_public_access(self):
        self.visibility('PUBLIC'); self.item.delete()
        self.assertEqual(self.api.get('/media/' + self.item.file.name).status_code, 404)
        self.assertTrue(Path(self.directory.name, self.item.file.name).exists())

    def test_jwt_native_access_cannot_bypass_authorization(self):
        self.api.force_authenticate(user=None)
        self.api.credentials(HTTP_AUTHORIZATION='Bearer ' + str(AccountRefreshToken.for_user(self.viewer).access_token))
        self.assertEqual(self.api.get(f'/api/portfolio/{self.item.pk}/').status_code, 404)
        self.assertEqual(self.api.get('/media/' + self.item.file.name).status_code, 404)
        self.api.credentials(HTTP_AUTHORIZATION='Bearer ' + str(AccountRefreshToken.for_user(self.owner).access_token))
        self.assertEqual(self.api.get(f'/api/portfolio/{self.item.pk}/').status_code, 200)

    def test_cloud_acl_is_checked_before_any_provider_request_and_preserves_legacy_access(self):
        self.item.file = 'media/portfolio/files/cloud-work.pdf'; self.item.save(update_fields=['file'])
        remote = Mock(status_code=200, headers={'Content-Type': 'application/pdf', 'Content-Length': str(len(self.pdf))})
        remote.iter_content.return_value = iter([self.pdf])
        missing = Mock(status_code=404)
        with override_settings(STORAGES={'default': {'BACKEND': 'config.media_storage.PlaybackMediaStorage'},
            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}), \
             patch('config.media_views._cloud_url', return_value='https://cloudinary.invalid/signed'), \
             patch('requests.Session.get', side_effect=[missing, remote]) as fetch:
            path = '/media/portfolio/files/cloud-work.pdf'
            self.as_user(self.viewer)
            self.assertEqual(self.api.get(path).status_code, 404)
            self.assertEqual(self.api.head(path).status_code, 404)
            fetch.assert_not_called()
            self.as_user(self.owner)
            response = self.api.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b''.join(response.streaming_content), self.pdf)
            self.assertNotIn('cloudinary.invalid', response.get('Location', ''))

    @patch('cloudinary.uploader.upload')
    def test_new_cloud_portfolio_images_and_files_start_private(self, upload):
        storage = PlaybackMediaStorage()
        for name, content in [('portfolio/images/new.png', self.png), ('portfolio/files/new.pdf', self.pdf)]:
            with self.subTest(name=name):
                storage._upload(name, ContentFile(content))
                self.assertEqual(upload.call_args.kwargs['type'], 'authenticated')

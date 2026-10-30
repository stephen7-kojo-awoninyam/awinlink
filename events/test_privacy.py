import tempfile
import io
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import User
from organizations.models import Organization, OrganizationMembership
from config.media_storage import PlaybackMediaStorage
from .models import Event, EventMedia, EventFeedback, EventRegistration


class EventPrivacyTests(TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        override = override_settings(MEDIA_ROOT=directory.name, STORAGES={
            'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
        override.enable(); self.addCleanup(override.disable)
        self.owner = User.objects.create_user('event-owner', role='ORGANIZATION')
        self.member = User.objects.create_user('event-member', role='COACH')
        self.outsider = User.objects.create_user('event-outsider', role='SCOUT')
        self.org = Organization.objects.create(user=self.owner, name='Event organization', status='ACTIVE')
        OrganizationMembership.objects.create(user=self.owner, organization=self.org, role='OWNER')
        self.membership = OrganizationMembership.objects.create(user=self.member, organization=self.org, role='VIEWER')
        now = timezone.now()
        self.event = Event.objects.create(organizer=self.org, title='Draft event marker', slug='draft-event-marker',
            description='Private event description marker', status='DRAFT', event_type='WEBINAR', location='Online',
            online=True, meeting_link='https://example.invalid/private-meeting-marker', start_date=now+timedelta(days=2),
            end_date=now+timedelta(days=3), registration_deadline=now+timedelta(days=1))
        self.data = b'\x89PNG\r\n\x1a\noriginal image fixture'
        self.name = FileSystemStorage().save('events/gallery/private.png', ContentFile(self.data))
        self.image = FileSystemStorage().save('events/images/private.png', ContentFile(self.data))
        self.event.image = self.image; self.event.save()
        self.media = EventMedia.objects.create(event=self.event, uploaded_by=self.org, media_type='IMAGE', file=self.name, caption='Private gallery marker')
        EventFeedback.objects.create(event=self.event, reviewer=self.owner, rating=5, comment='Private feedback marker')
        self.api = APIClient()

    def assert_reads(self, actor, status):
        self.api.force_authenticate(actor)
        for path in (f'/api/events/{self.event.pk}/', f'/api/events/{self.event.pk}/media/',
                     f'/api/events/{self.event.pk}/feedback/list/', f'/events/{self.event.pk}/', f'/events/{self.event.pk}/gallery/'):
            if path.startswith('/api/'):
                response = self.api.get(path); expected = status
            else:
                self.client.force_login(actor)
                response = self.client.get(path)
                expected = status if User.objects.filter(pk=actor.pk, is_active=True).exists() else 302
            self.assertEqual(response.status_code, expected, (path, getattr(response, 'data', None)))
            if expected != 302: self.assertIn('no-store', response['Cache-Control'])
            if status == 404:
                for value in (self.event.description, self.event.meeting_link, self.media.caption):
                    self.assertNotIn(value.encode(), response.content)
        for name in (self.image, self.name):
            for method in ('get', 'head'):
                response = getattr(self.api, method)('/media/' + name)
                self.assertEqual(response.status_code, status); self.assertIn('no-store', response['Cache-Control'])
                if status == 200 and method == 'get': self.assertEqual(b''.join(response.streaming_content), self.data)
                response.close()

    def test_draft_parent_children_web_and_original_files_deny_unrelated_roles(self):
        for role in ('ATHLETE', 'COACH', 'SCOUT', 'ORGANIZATION', 'ADMIN'):
            self.outsider.role = role; self.outsider.is_staff = True; self.outsider.is_superuser = True; self.outsider.save()
            self.assert_reads(self.outsider, 404)
        self.api.force_authenticate(self.outsider)
        self.assertEqual(self.api.get('/api/events/').data, [])

    def test_current_owner_and_viewer_member_can_read_draft_and_private_files(self):
        for user in (self.owner, self.member): self.assert_reads(user, 200)
        self.api.force_authenticate(self.owner)
        result = self.api.get('/api/events/my/')
        self.assertEqual(result.data[0]['id'], self.event.pk)
        self.assertEqual(result.data[0]['meeting_link'], self.event.meeting_link)

    def test_view_permission_never_grants_event_management(self):
        self.api.force_authenticate(self.member)
        result = self.api.put(f'/api/events/{self.event.pk}/update/', {'title': 'changed'}, format='json')
        self.assertEqual(result.status_code, 403)
        self.event.refresh_from_db(); self.assertEqual(self.event.title, 'Draft event marker')
        self.api.force_authenticate(self.owner)
        self.assertEqual(self.api.put(f'/api/events/{self.event.pk}/update/', {'title': 'Owner update'}, format='json').status_code, 200)

    def test_removed_or_suspended_membership_revokes_existing_reads(self):
        for status in ('REMOVED', 'SUSPENDED'):
            self.membership.status = status; self.membership.save()
            self.assert_reads(self.member, 404)

    def test_suspended_org_and_inactive_actor_or_owner_are_denied(self):
        self.org.status = 'SUSPENDED'; self.org.save()
        self.assert_reads(self.owner, 404)
        self.org.status = 'ACTIVE'; self.org.save()
        User.objects.filter(pk=self.member.pk).update(is_active=False)
        self.assert_reads(self.member, 404)
        User.objects.filter(pk=self.owner.pk).update(is_active=False)
        self.assert_reads(self.owner, 404)

    def test_parent_denial_is_enforced_when_child_lists_are_empty(self):
        self.event.media.all().delete(); self.event.feedback.all().delete()
        self.api.force_authenticate(self.outsider)
        for path in ('media', 'feedback/list'):
            self.assertEqual(self.api.get(f'/api/events/{self.event.pk}/{path}/').status_code, 404)

    def test_published_access_and_republishing_preserve_records_and_original_bytes(self):
        self.event.status = 'PUBLISHED'; self.event.save()
        self.assert_reads(self.outsider, 200)
        self.api.force_authenticate(None)
        for name in (self.name, self.image):
            response = self.api.get('/media/' + name); self.assertEqual(response.status_code, 200); response.close()
        self.event.status = 'DRAFT'; self.event.save()
        self.assert_reads(self.outsider, 404)
        self.assertEqual(EventMedia.objects.filter(pk=self.media.pk).count(), 1)
        self.assertEqual(Path(FileSystemStorage().path(self.name)).read_bytes(), self.data)

    def test_publication_filters_inactive_organizer_accounts(self):
        self.event.status = 'PUBLISHED'; self.event.save()
        User.objects.filter(pk=self.owner.pk).update(is_active=False)
        self.api.force_authenticate(self.outsider)
        self.assertEqual(self.api.get('/api/events/').data, [])
        self.assert_reads(self.outsider, 404)
        self.client.force_login(self.outsider)
        self.assertNotContains(self.client.get('/explore/'), self.event.title)

    def test_ordinary_participant_cannot_read_an_event_returned_to_draft(self):
        from talents.models import TalentProfile
        talent = TalentProfile.objects.create(user=self.outsider)
        EventRegistration.objects.create(event=self.event, talent=talent, status='APPROVED')
        self.assert_reads(self.outsider, 404)

    def test_web_interactions_cannot_create_activity_on_hidden_drafts(self):
        self.client.force_login(self.outsider)
        for action in ('like', 'comment', 'register', 'feedback'):
            response = self.client.post(f'/events/{self.event.pk}/{action}/', {'text': 'comment', 'rating': 5})
            self.assertIn(response.status_code, (403, 404))
        self.assertEqual(self.event.likes.count(), 0); self.assertEqual(self.event.comments.count(), 0)

    def test_orphaned_event_files_are_denied_without_deleting_bytes(self):
        self.media.delete(); self.event.image = ''; self.event.save()
        self.api.force_authenticate(self.owner)
        for name in (self.name, self.image):
            self.assertEqual(self.api.get('/media/' + name).status_code, 404)
            self.assertTrue(FileSystemStorage().exists(name))

    def test_gallery_delete_requires_manager_revokes_reference_and_retains_bytes(self):
        from media_erasure.models import MediaErasureJob
        outsider_client = self.client
        outsider_client.force_login(self.outsider)
        delete_url = f'/events/gallery/delete/{self.media.pk}/'
        self.assertEqual(outsider_client.post(delete_url).status_code, 403)
        self.assertTrue(EventMedia.objects.filter(pk=self.media.pk).exists())
        from media_erasure.models import MediaErasureJob
        self.assertFalse(MediaErasureJob.objects.exists())

        self.client.force_login(self.owner)
        self.api.force_authenticate(self.owner)
        before = self.api.get('/media/' + self.name)
        self.assertEqual(before.status_code, 200)
        before.close()
        response = self.client.post(delete_url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(EventMedia.objects.filter(pk=self.media.pk).exists())
        self.assertTrue(MediaErasureJob.objects.filter(source_model='events.eventmedia',
            source_pk=str(self.media.pk), source_field='file').exists())
        self.api.force_authenticate(self.owner)
        denied = self.api.get('/media/' + self.name)
        self.assertEqual(denied.status_code, 404)
        denied.close()
        # The retained object is no longer addressable through the app. A
        # provider erasure job needs explicit retention and delivery metadata.
        self.assertTrue(FileSystemStorage().exists(self.name))

    def test_event_delete_revokes_all_child_media_and_retains_originals(self):
        from media_erasure.models import MediaErasureJob
        event_id = self.event.pk
        names = (self.name, self.image)
        self.api.force_authenticate(self.owner)
        deleted = self.api.delete(f'/api/events/{event_id}/delete/')
        self.assertEqual(deleted.status_code, 204)
        queued = MediaErasureJob.objects.filter(source_model__in=('events.event', 'events.eventmedia'))
        self.assertEqual(queued.count(), 2)
        self.assertEqual(set(queued.values_list('source_field', flat=True)), {'image', 'file'})
        for name in names:
            denied = self.api.get('/media/' + name)
            self.assertEqual(denied.status_code, 404)
            denied.close()
            self.assertTrue(FileSystemStorage().exists(name))

    def test_replaced_event_image_is_queued_and_original_remains(self):
        from media_erasure.models import MediaErasureJob
        old_name = self.event.image.name
        image = io.BytesIO()
        Image.new('RGB', (2, 2), 'green').save(image, format='PNG')
        self.api.force_authenticate(self.owner)
        response = self.api.put(f'/api/events/{self.event.pk}/update/',
            {'image': SimpleUploadedFile('replacement.png', image.getvalue(), 'image/png')}, format='multipart')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(MediaErasureJob.objects.filter(storage_name=old_name, source_field='image',
            source_model='events.event').exists())
        self.assertTrue(FileSystemStorage().exists(old_name))

    def test_native_jwt_obeys_the_same_draft_permission(self):
        for user, expected in ((self.owner, 200), (self.member, 200), (self.outsider, 404)):
            client = APIClient(); client.credentials(HTTP_AUTHORIZATION='Bearer ' + str(AccessToken.for_user(user)))
            result = client.get(f'/api/events/{self.event.pk}/'); self.assertEqual(result.status_code, expected)

    def test_cloud_authorization_precedes_provider_fetch_and_keeps_provider_url_private(self):
        self.media.file = 'media/events/gallery/opaque'; self.media.save()
        storage = PlaybackMediaStorage(); session = Mock(); remote = Mock(status_code=200)
        remote.headers = {'Content-Type': 'image/png', 'Content-Length': str(len(self.data))}
        remote.iter_content.return_value = iter([self.data]); session.get.return_value = remote
        with patch('config.media_views.default_storage', storage), patch('config.media_views.requests.Session', return_value=session), patch(
                'config.media_views._cloud_url', return_value='https://provider.invalid/signed-secret') as url:
            self.api.force_authenticate(self.outsider)
            self.assertEqual(self.api.get('/media/events/gallery/opaque').status_code, 404); session.get.assert_not_called()
            self.api.force_authenticate(self.member)
            result = self.api.get('/media/events/gallery/opaque')
            self.assertEqual(result.status_code, 200); self.assertTrue(url.call_args.kwargs['authenticated'])
            self.assertNotIn('signed-secret', str(result.headers)); self.assertEqual(b''.join(result.streaming_content), self.data); result.close()

    @patch('cloudinary.uploader.upload')
    def test_new_event_and_athlete_cloud_assets_start_authenticated(self, upload):
        for folder in ('events/images/', 'events/gallery/', 'athletes/profile/', 'athletes/cover/', 'athletes/media/', 'talents/profile/'):
            PlaybackMediaStorage()._upload(folder + 'safe.png', ContentFile(self.data))
            self.assertEqual(upload.call_args.kwargs['type'], 'authenticated')

    def test_historical_certificate_verification_keeps_attestation_without_leaking_draft_title(self):
        from talents.models import TalentProfile
        from .models import EventCertificate
        talent = TalentProfile.objects.create(user=self.outsider)
        certificate = EventCertificate.objects.create(event=self.event, talent=talent, issued_by=self.org,
            certificate_title='Historical certificate marker', certificate_code='historical-public-code')
        self.api.force_authenticate(self.outsider)
        result = self.api.get(f'/api/events/certificates/{certificate.certificate_code}/verify/')
        self.assertEqual(result.status_code, 200); self.assertEqual(result.data['event_title'], '')
        self.assertEqual(result.data['certificate_title'], certificate.certificate_title)
        self.assertNotIn(self.event.title, str(result.data))
        self.outsider.role = 'ATHLETE'; self.outsider.save()
        result = self.api.get('/api/events/my-certificates/')
        self.assertEqual(result.status_code, 200); self.assertEqual(result.data[0]['event_title'], '')
        self.client.force_login(self.outsider)
        for path in (f'/events/verify/{certificate.certificate_code}/', f'/events/certificate/{certificate.pk}/',
                     '/events/my-certificates/', '/events/certificates/'):
            result = self.client.get(path)
            self.assertEqual(result.status_code, 200); self.assertNotContains(result, self.event.title)
            self.assertContains(result, certificate.certificate_title)
        self.api.force_authenticate(self.owner)
        self.assertEqual(self.api.get(f'/api/events/certificates/{certificate.certificate_code}/verify/').data['event_title'], self.event.title)
        self.assertTrue(EventCertificate.objects.filter(pk=certificate.pk).exists())

from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from .models import ContentReport, ReportReviewEvent, User
from .report_review import review_report
from feed.models import Post


class ChildSafetyReportingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username='safety-reporter', date_of_birth=date(1990, 1, 1))
        self.other = User.objects.create_user(username='reported-user')
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def test_in_app_child_safety_category_preserves_private_target_access_checks(self):
        private = Post.objects.create(author=self.other, caption='private', visibility='PRIVATE')
        public = Post.objects.create(author=self.other, caption='public', visibility='PUBLIC')
        payload = {'target_type': 'post', 'target_id': private.pk, 'reason': 'child_safety', 'details': 'Concern about child safety'}
        self.assertEqual(self.api.post('/api/safety/reports/', payload, format='json').status_code, 404)
        payload['target_id'] = public.pk
        response = self.api.post('/api/safety/reports/', payload, format='json')
        self.assertEqual(response.status_code, 201)
        report = ContentReport.objects.get()
        self.assertEqual(report.reason, 'child_safety')
        self.assertEqual(report.reporter, self.user)
        self.assertEqual(report.status, 'OPEN')
        self.assertTrue(Post.objects.filter(pk=public.pk).exists())
        self.assertFalse(ReportReviewEvent.objects.exists())

    def test_general_in_app_incident_does_not_require_private_record_access(self):
        payload = {'target_type': 'safety', 'target_id': 0, 'reason': 'child_safety',
                   'details': 'Call/classroom concern; no private record lookup required',
                   'status': 'RESOLVED', 'contact_email': 'forged@example.com'}
        self.assertEqual(self.api.post('/api/safety/reports/', payload, format='json').status_code, 201)
        report = ContentReport.objects.get()
        self.assertEqual(report.target_id, 0)
        self.assertEqual(report.status, 'OPEN')
        self.assertEqual(report.contact_email, '')
        for changes in [{'reason': 'spam'}, {'target_id': 1}, {'details': 'tiny'}]:
            self.assertEqual(self.api.post('/api/safety/reports/', {**payload, **changes}, format='json').status_code, 400)
        self.assertEqual(APIClient().post('/api/safety/reports/', payload, format='json').status_code, 401)

    def test_public_contact_works_without_signin_or_email_and_exposes_no_report_data(self):
        self.assertEqual(self.client.get('/child-safety/report/').status_code, 200)
        response = self.client.post('/child-safety/report/', {'details': 'A child safety concern with a record link'})
        self.assertRedirects(response, '/child-safety/report/')
        report = ContentReport.objects.get()
        self.assertIsNone(report.reporter)
        self.assertEqual(report.reason, 'child_safety')
        self.assertEqual(report.contact_email, '')
        self.assertNotContains(self.client.get('/child-safety/report/'), report.details)
        self.assertEqual(self.client.get(f'/child-safety/report/{report.pk}/').status_code, 404)

    def test_contact_validates_input_csrf_and_rejects_attachments(self):
        self.assertEqual(Client(enforce_csrf_checks=True).post('/child-safety/report/', {'details': 'A real concern'}).status_code, 403)
        for data in [{'details': 'tiny'}, {'details': 'x' * 2001}, {'details': 'A real safety concern', 'contact_email': 'invalid'}]:
            self.assertEqual(self.client.post('/child-safety/report/', data).status_code, 400)
        self.assertEqual(self.client.post('/child-safety/report/', {'details': 'A real safety concern',
            'file': SimpleUploadedFile('not-evidence.txt', b'do not upload evidence')}).status_code, 400)
        self.assertFalse(ContentReport.objects.exists())
        csrf = Client(enforce_csrf_checks=True)
        csrf.get('/child-safety/report/')
        response = csrf.post('/child-safety/report/', {'csrfmiddlewaretoken': csrf.cookies['csrftoken'].value,
            'details': 'A real safety concern', 'contact_email': 'reply@example.com'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ContentReport.objects.get().contact_email, 'reply@example.com')

    def test_public_contact_handles_abuse_and_cache_database_outages_without_false_receipts(self):
        from .security import AuthenticationUnavailable
        with patch('core.safety_views.enforce_auth_limit', side_effect=AuthenticationUnavailable):
            self.assertEqual(self.client.post('/child-safety/report/', {'details': 'A real safety concern'}).status_code, 503)
        with patch('core.safety_views.ContentReport.objects.create', side_effect=DatabaseError('private failure')):
            response = self.client.post('/child-safety/report/', {'details': 'A real safety concern'})
        self.assertEqual(response.status_code, 503)
        self.assertNotContains(response, 'private failure', status_code=503)
        self.assertNotIn('safety_report_received', self.client.session)
        for _ in range(31):
            response = self.client.post('/child-safety/report/', {'details': 'tiny'})
        self.assertEqual(response.status_code, 429)
        self.assertIn('Retry-After', response)
        self.assertFalse(ContentReport.objects.exists())

    def test_restricted_child_can_use_only_standalone_public_intake(self):
        self.user.date_of_birth = date(timezone.localdate().year - 10, 1, 1)
        self.user.save()
        self.client.force_login(self.user)
        self.assertEqual(self.client.post('/child-safety/report/', {'details': 'Concern while my account is restricted'}).status_code, 302)
        self.assertEqual(self.client.get('/api/auth/me/').status_code, 403)
        self.assertEqual(self.client.post('/api/safety/reports/', {}).status_code, 403)
        self.assertIsNone(ContentReport.objects.get().reporter)


class ReportReviewTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username='reviewer', is_staff=True)
        self.staff.user_permissions.add(Permission.objects.get(codename='change_contentreport'))
        self.author = User.objects.create_user(username='post-author')
        self.post = Post.objects.create(author=self.author, caption='review target')
        self.report = ContentReport.objects.create(reporter=None, target_type='post', target_id=self.post.pk,
            reason='child_safety', details='A concern requiring human review')

    def review(self, **changes):
        return review_report(actor=self.staff, report_id=self.report.pk, new_status=changes.pop('new_status', 'REVIEWED'),
                             notes=changes.pop('notes', 'Reviewed and recorded the next action'), **changes)

    def test_review_requires_notes_and_review_permission_and_cannot_skip_to_resolution(self):
        for changes in [{'notes': ''}, {'new_status': 'RESOLVED'}, {'action': 'invented'}]:
            with self.assertRaises(ValidationError):
                self.review(**changes)
        self.staff.user_permissions.clear()
        with self.assertRaises(PermissionDenied):
            self.review()
        self.assertFalse(ReportReviewEvent.objects.exists())
        self.assertTrue(Post.objects.filter(pk=self.post.pk).exists())

    def test_transitions_record_actor_history_and_reopening_without_punishing_target(self):
        event = self.review()
        self.assertEqual((event.previous_status, event.new_status, event.actor), ('OPEN', 'REVIEWED', self.staff))
        self.review(new_status='ESCALATED')
        self.review(new_status='RESOLVED')
        self.review(new_status='REVIEWED')
        self.assertEqual(ReportReviewEvent.objects.count(), 4)
        self.assertTrue(Post.objects.filter(pk=self.post.pk).exists())

    def test_post_removal_requires_separate_permission_and_escalates_for_remaining_work(self):
        with self.assertRaises(PermissionDenied):
            self.review(action='REMOVE_POST', new_status='ESCALATED')
        self.staff.user_permissions.add(Permission.objects.get(codename='delete_post', content_type__app_label='feed'))
        event = self.review(action='REMOVE_POST', new_status='ESCALATED')
        self.assertEqual(event.action, 'REMOVE_POST')
        self.assertFalse(Post.objects.filter(pk=self.post.pk).exists())
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, 'ESCALATED')
        self.assertTrue(User.objects.filter(pk=self.author.pk, is_active=True).exists())

    def test_audit_failure_rolls_back_post_removal(self):
        self.staff.user_permissions.add(Permission.objects.get(codename='delete_post', content_type__app_label='feed'))
        with patch('accounts.report_review.ReportReviewEvent.objects.create', side_effect=ValueError('audit failed')):
            with self.assertRaises(ValueError):
                self.review(action='REMOVE_POST', new_status='ESCALATED')
        self.assertTrue(Post.objects.filter(pk=self.post.pk).exists())
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, 'OPEN')

    def test_admin_review_requires_csrf_and_read_permission_does_not_grant_review(self):
        url = reverse('admin:accounts_report_review', args=[self.report.pk])
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.staff)
        self.assertEqual(csrf.post(url, {'new_status': 'REVIEWED', 'notes': 'Reviewed carefully', 'action': 'REVIEW'}).status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('admin:accounts_contentreport_changelist')).status_code, 200)
        self.assertEqual(self.client.post(url, {'new_status': 'REVIEWED', 'notes': 'Reviewed carefully', 'action': 'REVIEW'}).status_code, 302)
        self.assertContains(self.client.get(url), 'Reviewed carefully')
        self.staff.user_permissions.clear()
        self.staff.user_permissions.add(Permission.objects.get(codename='view_contentreport'))
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_review_notes_are_escaped_and_generic_admin_cannot_skip_audit(self):
        self.review(notes='<script>not executable evidence</script>')
        self.client.force_login(self.staff)
        url = reverse('admin:accounts_report_review', args=[self.report.pk])
        self.assertNotContains(self.client.get(url), '<script>not executable evidence</script>')
        response = self.client.post(reverse('admin:accounts_contentreport_change', args=[self.report.pk]), {'status': 'RESOLVED'})
        self.assertEqual(response.status_code, 403)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, 'REVIEWED')
        self.assertEqual(ReportReviewEvent.objects.count(), 1)

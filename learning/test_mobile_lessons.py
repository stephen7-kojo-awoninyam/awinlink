import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from learning.models import Certificate, Course, Enrollment, Lesson, LessonProgress, LearningCategory


@override_settings(STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                              'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class MobileLessonTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='mobile-learner', role='ATHLETE')
        self.client.force_authenticate(self.user)
        category = LearningCategory.objects.create(name='Mobile lessons')
        self.course = Course.objects.create(creator=self.user, category=category, title='Course', slug='mobile-course', description='Test', status='DRAFT')

    def test_multipart_lesson_files_are_saved(self):
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            response = self.client.post(f'/api/learning/courses/{self.course.pk}/lessons/create/', {
                'title': 'Lesson', 'description': 'Description', 'order': '1', 'duration': '3',
                'notes': SimpleUploadedFile('notes.txt', b'Lesson notes', content_type='text/plain'),
            }, format='multipart')
            self.assertEqual(response.status_code, 201, response.data)
            self.assertTrue(response.data['notes'].endswith('notes.txt'))
            self.assertEqual(Lesson.objects.get(pk=response.data['id']).course, self.course)

    def test_valid_webvtt_and_readable_transcript_are_saved_through_creator_api(self):
        captions = b'WEBVTT\n\n00:00:01.000 --> 00:00:02.500\nHello learners\n'
        response = self.client.post(f'/api/learning/courses/{self.course.pk}/lessons/create/', {
            'title': 'Captioned lesson', 'order': '1', 'caption_language': 'en-US',
            'transcript': 'Welcome to this lesson.',
            'captions': SimpleUploadedFile('lesson.vtt', captions, content_type='text/vtt'),
        }, format='multipart')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data['captions'].endswith('.vtt'))
        self.assertEqual(response.data['caption_language'], 'en-US')
        self.assertEqual(response.data['transcript'], 'Welcome to this lesson.')

    def test_invalid_caption_and_language_are_rejected_without_lesson_creation(self):
        invalid = [
            ('lesson.txt', b'WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHello\n', 'en'),
            ('lesson.vtt', b'WEBVTT\n\n00:00:03.000 --> 00:00:02.000\nHello\n', 'en'),
            ('lesson.vtt', b'<html>unsafe</html>', 'en'),
            ('lesson.vtt', b'WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHello\n', 'en<script>'),
        ]
        for filename, content, language in invalid:
            with self.subTest(filename=filename, language=language):
                response = self.client.post(f'/api/learning/courses/{self.course.pk}/lessons/create/', {
                    'title': 'Invalid caption', 'caption_language': language,
                    'captions': SimpleUploadedFile(filename, content, content_type='text/vtt'),
                }, format='multipart')
                self.assertEqual(response.status_code, 400, getattr(response, 'data', response.content))
        self.assertFalse(self.course.lessons.exists())

    def test_transcript_length_is_bounded(self):
        response = self.client.post(f'/api/learning/courses/{self.course.pk}/lessons/create/', {
            'title': 'Long transcript', 'transcript': 'x' * 100001,
        }, format='multipart')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.course.lessons.exists())

    def test_caption_patch_preserves_existing_video_and_obeys_course_edit_lock(self):
        lesson = Lesson.objects.create(course=self.course, title='Keep the video', order=1, video='learning/videos/existing.mp4')
        response = self.client.patch(f'/api/learning/lessons/{lesson.pk}/', {
            'caption_language': 'en', 'transcript': 'New transcript.',
            'captions': SimpleUploadedFile('lesson.vtt', b'WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nNew caption\n', content_type='text/vtt'),
        }, format='multipart')
        self.assertEqual(response.status_code, 200, getattr(response, 'data', response.content))
        lesson.refresh_from_db()
        self.assertEqual(lesson.video.name, 'learning/videos/existing.mp4')
        self.assertEqual(lesson.transcript, 'New transcript.')
        self.assertTrue(lesson.captions.name.endswith('.vtt'))
        self.course.status = 'PENDING'
        self.course.save()
        self.assertEqual(self.client.patch(f'/api/learning/lessons/{lesson.pk}/', {'transcript': 'Locked edit.'}).status_code, 400)

    def test_completed_lesson_ids_survive_new_progress_request(self):
        enrollment = Enrollment.objects.create(user=self.user, course=self.course)
        lesson = Lesson.objects.create(course=self.course, title='First', order=1)
        other = Lesson.objects.create(course=self.course, title='Second', order=2)
        LessonProgress.objects.create(enrollment=enrollment, lesson=lesson, completed=True)
        LessonProgress.objects.create(enrollment=enrollment, lesson=other, completed=False)
        response = self.client.get(f'/api/learning/courses/{self.course.pk}/progress/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['completed_lesson_ids'], [lesson.pk])

    def test_paid_enrollment_cannot_bypass_missing_store_billing(self):
        self.course.is_free = False
        self.course.status = 'APPROVED'
        self.course.save()
        response = self.client.post(f'/api/learning/courses/{self.course.pk}/enroll/')
        self.assertEqual(response.status_code, 402)
        self.assertFalse(Enrollment.objects.filter(course=self.course).exists())

    def test_paid_assets_are_redacted_until_enrolled(self):
        self.course.is_free = False
        self.course.status = 'APPROVED'
        self.course.save()
        lesson = Lesson.objects.create(course=self.course, title='Paid', order=1, video='learning/videos/private.mp4', notes='learning/notes/private.txt', captions='learning/captions/private.vtt', caption_language='en', transcript='secret transcript')
        learner = get_user_model().objects.create_user(username='unpaid-learner')
        self.client.force_authenticate(learner)
        response = self.client.get(f'/api/learning/courses/{self.course.pk}/lessons/')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data[0]['video'])
        self.assertIsNone(response.data[0]['notes'])
        self.assertIsNone(response.data[0]['captions'])
        self.assertEqual(response.data[0]['transcript'], '')
        self.assertTrue(response.data[0]['is_locked'])
        self.assertEqual(self.client.get(f'/api/learning/lessons/{lesson.pk}/').status_code, 403)

    def test_server_appends_after_all_lessons_without_reordering_existing_data(self):
        first = Lesson.objects.create(course=self.course, title='First', order=1)
        last = Lesson.objects.create(course=self.course, title='Beyond first page', order=90)
        for supplied_order, expected in [(None, 91), ('2', 92)]:
            data = {'title': 'Appended', 'duration': '2'}
            if supplied_order is not None:
                data['order'] = supplied_order
            response = self.client.post(f'/api/learning/courses/{self.course.pk}/lessons/create/', data, format='multipart')
            self.assertEqual(response.status_code, 201, response.data)
            self.assertEqual(response.data['order'], expected)
        first.refresh_from_db()
        last.refresh_from_db()
        self.assertEqual((first.order, last.order), (1, 90))

    def test_server_ordering_preserves_creator_and_moderation_guards(self):
        outsider = get_user_model().objects.create_user(username='other-creator', role='SCOUT')
        self.client.force_authenticate(outsider)
        url = f'/api/learning/courses/{self.course.pk}/lessons/create/'
        self.assertEqual(self.client.post(url, {'title': 'Blocked'}).status_code, 403)
        self.client.force_authenticate(self.user)
        for state in ['PENDING', 'APPROVED']:
            self.course.status = state
            self.course.save()
            self.assertEqual(self.client.post(url, {'title': 'Blocked'}).status_code, 400)
        self.assertFalse(self.course.lessons.exists())

    def test_locked_preview_exemptions_and_empty_media_are_explicit(self):
        self.course.is_free = False
        self.course.status = 'APPROVED'
        self.course.save()
        Lesson.objects.create(course=self.course, title='No assets yet', order=1)
        url = f'/api/learning/courses/{self.course.pk}/lessons/'
        self.assertFalse(self.client.get(url).data[0]['is_locked'])  # owner
        admin = get_user_model().objects.create_user(username='preview-admin', role='ADMIN')
        self.client.force_authenticate(admin)
        self.assertFalse(self.client.get(url).data[0]['is_locked'])
        learner = get_user_model().objects.create_user(username='preview-learner')
        self.client.force_authenticate(learner)
        self.assertTrue(self.client.get(url).data[0]['is_locked'])
        Enrollment.objects.create(course=self.course, user=learner)
        self.assertFalse(self.client.get(url).data[0]['is_locked'])
        Enrollment.objects.filter(user=learner).delete()
        self.course.is_free = True
        self.course.save()
        self.assertFalse(self.client.get(url).data[0]['is_locked'])

    def test_invalid_lesson_still_rejected_without_writes(self):
        response = self.client.post(f'/api/learning/courses/{self.course.pk}/lessons/create/', {'title': '', 'duration': '-1'})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.course.lessons.exists())

    def test_certificate_course_route_is_owner_scoped(self):
        enrollment = Enrollment.objects.create(course=self.course, user=self.user, completed=True)
        Certificate.objects.create(enrollment=enrollment, certificate_id='MOBILE-STABLE-AWARD')
        response = self.client.get('/api/learning/my-certificates/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]['course_id'], self.course.pk)
        self.assertEqual(response.data[0]['certificate_id'], 'MOBILE-STABLE-AWARD')
        self.assertIsNone(response.data[0]['pdf'])
        other = get_user_model().objects.create_user(username='other-certificate-owner')
        self.client.force_authenticate(other)
        self.assertEqual(self.client.get('/api/learning/my-certificates/').data, [])

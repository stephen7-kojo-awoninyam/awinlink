import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from learning.models import Course, Enrollment, Lesson, LessonProgress, LearningCategory


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
        lesson = Lesson.objects.create(course=self.course, title='Paid', order=1, video='learning/videos/private.mp4', notes='learning/notes/private.txt')
        learner = get_user_model().objects.create_user(username='unpaid-learner')
        self.client.force_authenticate(learner)
        response = self.client.get(f'/api/learning/courses/{self.course.pk}/lessons/')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data[0]['video'])
        self.assertIsNone(response.data[0]['notes'])
        self.assertEqual(self.client.get(f'/api/learning/lessons/{lesson.pk}/').status_code, 403)

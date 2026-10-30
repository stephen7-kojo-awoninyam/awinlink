from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import CourseModule, Enrollment, Lesson
from .test_classroom_security import ClassroomFixture


class CourseLiveSessionsAPITests(ClassroomFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.module = CourseModule.objects.create(course=self.course, title='Foundation unit', order=1)
        self.lesson.module = self.module
        self.lesson.save(update_fields=['module'])
        self.client = APIClient()

    def get_sessions(self, user, suffix=''):
        self.client.force_authenticate(user)
        return self.client.get(f'/api/learning/courses/{self.course.pk}/live-sessions/{suffix}')

    def test_enrolled_learner_gets_lesson_and_optional_section_context(self):
        response = self.get_sessions(self.learner)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Cache-Control'].find('no-store') >= 0)
        self.assertEqual(len(response.data['results']), 1)
        row = response.data['results'][0]
        self.assertEqual((row['course'], row['lesson'], row['module']), (self.course.pk, self.lesson.pk, self.module.pk))
        self.assertEqual((row['lesson_title'], row['module_title'], row['classroom_title']),
            (self.lesson.title, self.module.title, self.classroom.title))

    def test_schedule_can_be_filtered_by_its_lesson_and_is_hidden_when_access_is_revoked(self):
        self.assertEqual(len(self.get_sessions(self.learner, f'?lesson={self.lesson.pk}').data['results']), 1)
        other_lesson = Lesson.objects.create(course=self.course, title='Another lesson', order=2)
        self.assertEqual(self.get_sessions(self.learner, f'?lesson={other_lesson.pk}').data['results'], [])
        Enrollment.objects.filter(user=self.learner, course=self.course).delete()
        self.assertEqual(self.get_sessions(self.learner).data['results'], [])

    def test_unrelated_account_and_admin_role_do_not_bypass_classroom_visibility(self):
        outsider = get_user_model().objects.create_user(username='course-session-outsider')
        admin = get_user_model().objects.create_user(username='course-session-admin', role='ADMIN', is_staff=True)
        self.assertEqual(self.get_sessions(outsider).data['results'], [])
        self.assertEqual(self.get_sessions(admin).data['results'], [])

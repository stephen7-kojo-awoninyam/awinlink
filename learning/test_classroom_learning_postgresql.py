import unittest

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from rest_framework.test import APIClient

from .models import CourseModule
from .test_classroom_security import ClassroomFixture


@unittest.skipUnless(connection.vendor == 'postgresql', 'Requires the disposable PostgreSQL audit database.')
class CourseLiveSessionsPostgreSQLTests(ClassroomFixture, TestCase):
    def test_postgresql_course_lesson_module_session_join_preserves_visibility_and_order(self):
        first = CourseModule.objects.create(course=self.course, title='First section', order=1)
        second = CourseModule.objects.create(course=self.course, title='Second section', order=2)
        self.lesson.module = second
        self.lesson.save(update_fields=['module'])

        client = APIClient()
        client.force_authenticate(self.learner)
        response = client.get(f'/api/learning/courses/{self.course.pk}/live-sessions/?lesson={self.lesson.pk}')
        self.assertEqual(response.status_code, 200)
        session = response.data['results'][0]
        self.assertEqual(session['course'], self.course.pk)
        self.assertEqual(session['module'], second.pk)
        self.assertEqual(session['module_title'], 'Second section')
        self.assertEqual(list(self.course.modules.values_list('order', flat=True)), [1, 2])

        unrelated = APIClient()
        outsider = get_user_model().objects.create_user(username='pg-course-session-outsider')
        unrelated.force_authenticate(outsider)
        self.assertEqual(unrelated.get(f'/api/learning/courses/{self.course.pk}/live-sessions/').data['results'], [])

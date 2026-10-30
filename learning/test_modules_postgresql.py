from django.contrib.auth import get_user_model
from django.db import connection
import unittest

from django.test import TestCase

from learning.models import Certificate, Course, CourseModule, Enrollment, LearningCategory, Lesson, LessonProgress, Quiz, QuizAttempt


class CourseModulePostgreSQLIntegrityTests(TestCase):
    """Exercise the new nullable relation against PostgreSQL when configured."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if connection.vendor != 'postgresql':
            raise unittest.SkipTest('Requires the disposable PostgreSQL audit database.')

    def test_existing_lesson_history_survives_module_assignment_and_delete(self):
        creator = get_user_model().objects.create_user(username='pg-module-creator', role='COACH')
        learner = get_user_model().objects.create_user(username='pg-module-learner', role='ATHLETE')
        category = LearningCategory.objects.create(name='PostgreSQL modules')
        course = Course.objects.create(creator=creator, category=category, title='Existing course', slug='pg-module-course', description='Existing course data')
        lesson = Lesson.objects.create(course=course, title='Existing lesson', order=7)
        quiz = Quiz.objects.create(lesson=lesson, title='Existing quiz')
        enrollment = Enrollment.objects.create(user=learner, course=course, completed=True)
        progress = LessonProgress.objects.create(enrollment=enrollment, lesson=lesson, completed=True)
        attempt = QuizAttempt.objects.create(enrollment=enrollment, quiz=quiz, score=1, total_questions=1, percentage=100, passed=True)
        certificate = Certificate.objects.create(enrollment=enrollment, certificate_id='PG-MODULE-CERT')

        module = CourseModule.objects.create(course=course, title='Section', order=1)
        lesson.module = module
        lesson.save(update_fields=['module'])
        lesson.refresh_from_db()
        self.assertEqual(lesson.order, 7)
        self.assertEqual(lesson.quiz.pk, quiz.pk)
        self.assertEqual(LessonProgress.objects.get(pk=progress.pk).lesson_id, lesson.pk)
        self.assertEqual(QuizAttempt.objects.get(pk=attempt.pk).quiz_id, quiz.pk)
        self.assertEqual(Certificate.objects.get(pk=certificate.pk).enrollment_id, enrollment.pk)

        module.delete()
        lesson.refresh_from_db()
        self.assertIsNone(lesson.module_id)
        self.assertEqual(Lesson.objects.get(pk=lesson.pk).order, 7)
        self.assertTrue(LessonProgress.objects.get(pk=progress.pk).completed)
        self.assertEqual(Quiz.objects.get(pk=quiz.pk).lesson_id, lesson.pk)
        self.assertTrue(QuizAttempt.objects.get(pk=attempt.pk).passed)
        self.assertEqual(Certificate.objects.get(pk=certificate.pk).certificate_id, 'PG-MODULE-CERT')

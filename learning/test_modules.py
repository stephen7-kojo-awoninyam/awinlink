from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from learning.curriculum import group_course_lessons
from learning.models import (Certificate, Course, CourseModule, Enrollment, LearningCategory,
                             Lesson, LessonProgress, Quiz, QuizAttempt)


class CourseModuleWorkflowTests(TestCase):
    def setUp(self):
        self.creator = get_user_model().objects.create_user(username='module-creator', role='COACH')
        self.learner = get_user_model().objects.create_user(username='module-learner', role='ATHLETE')
        self.course = Course.objects.create(creator=self.creator, category=LearningCategory.objects.create(name='Modules'),
            title='Grouped course', slug='grouped-course', description='Course with optional sections')
        self.client = APIClient()
        self.client.force_authenticate(self.creator)

    def create_module(self, title):
        return self.client.post(f'/api/learning/courses/{self.course.pk}/modules/', {'title': title}, format='json')

    def test_modules_order_and_lesson_grouping_leave_legacy_lesson_order_unchanged(self):
        first = self.create_module('Foundations')
        second = self.create_module('Advanced')
        self.assertEqual((first.status_code, second.status_code), (201, 201))
        self.assertEqual((first.data['order'], second.data['order']), (1, 2))
        lessons = [
            Lesson.objects.create(course=self.course, title='Later lesson', order=9, module_id=first.data['id']),
            Lesson.objects.create(course=self.course, title='Earlier legacy order', order=1, module_id=second.data['id']),
            Lesson.objects.create(course=self.course, title='Unassigned lesson', order=2),
        ]
        rows = self.client.get(f'/api/learning/courses/{self.course.pk}/lessons/').data
        self.assertEqual([row['id'] for row in rows], [lessons[1].pk, lessons[2].pk, lessons[0].pk])
        ordered, sections = group_course_lessons(self.course, Lesson.objects.filter(course=self.course).order_by('order', 'pk'))
        self.assertEqual([item.pk for item in ordered], [lessons[0].pk, lessons[1].pk, lessons[2].pk])
        self.assertEqual([section['title'] for section in sections], ['Foundations', 'Advanced', 'Other lessons'])
        self.assertEqual([item.order for item in lessons], [9, 1, 2])

    def test_module_reordering_and_assignment_reject_cross_course_modules(self):
        first = self.create_module('First').data
        second = self.create_module('Second').data
        updated = self.client.patch(f"/api/learning/modules/{first['id']}/", {'order': 3}, format='json')
        self.assertEqual(updated.status_code, 200)
        self.assertEqual([item['id'] for item in self.client.get(f'/api/learning/courses/{self.course.pk}/modules/').data], [second['id'], first['id']])
        lesson_response = self.client.post(f'/api/learning/courses/{self.course.pk}/lessons/create/',
            {'title': 'Mapped lesson', 'module': second['id']}, format='json')
        self.assertEqual(lesson_response.status_code, 201, lesson_response.data)
        other_course = Course.objects.create(creator=self.creator, category=self.course.category, title='Other', slug='other-course', description='Other')
        other_module = CourseModule.objects.create(course=other_course, title='Wrong course', order=1)
        rejected = self.client.patch(f"/api/learning/lessons/{lesson_response.data['id']}/", {'module': other_module.pk}, format='json')
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(Lesson.objects.get(pk=lesson_response.data['id']).module_id, second['id'])

    def test_module_deletion_unassigns_lesson_without_touching_learning_history(self):
        module_response = self.create_module('Keep history')
        module = CourseModule.objects.get(pk=module_response.data['id'])
        lesson = Lesson.objects.create(course=self.course, title='Has history', order=1, module=module)
        quiz = Quiz.objects.create(lesson=lesson, title='Existing assessment')
        enrollment = Enrollment.objects.create(user=self.learner, course=self.course, completed=True)
        progress = LessonProgress.objects.create(enrollment=enrollment, lesson=lesson, completed=True)
        attempt = QuizAttempt.objects.create(enrollment=enrollment, quiz=quiz, score=1, total_questions=1, percentage=100, passed=True)
        certificate = Certificate.objects.create(enrollment=enrollment, certificate_id='MODULE-HISTORY-CERT')
        self.assertEqual(self.client.delete(f'/api/learning/modules/{module.pk}/').status_code, 204)
        lesson.refresh_from_db()
        self.assertIsNone(lesson.module_id)
        self.assertEqual(LessonProgress.objects.get(pk=progress.pk).lesson_id, lesson.pk)
        self.assertEqual(Quiz.objects.get(pk=quiz.pk).lesson_id, lesson.pk)
        self.assertEqual(QuizAttempt.objects.get(pk=attempt.pk).quiz_id, quiz.pk)
        self.assertEqual(Certificate.objects.get(pk=certificate.pk).enrollment_id, enrollment.pk)

    def test_module_mutation_respects_creator_and_moderation_guards(self):
        module = self.create_module('Owner only').data
        outsider = get_user_model().objects.create_user(username='module-outsider', role='COACH')
        self.client.force_authenticate(outsider)
        self.assertEqual(self.client.patch(f"/api/learning/modules/{module['id']}/", {'order': 3}, format='json').status_code, 403)
        self.client.force_authenticate(self.creator)
        for state in ['PENDING', 'APPROVED']:
            self.course.status = state
            self.course.save()
            self.assertEqual(self.create_module('Blocked').status_code, 400)
            self.assertEqual(self.client.patch(f"/api/learning/modules/{module['id']}/", {'order': 3}, format='json').status_code, 400)

    def test_published_paid_course_hides_modules_and_keeps_lesson_media_locked(self):
        module = self.create_module('Private course section').data
        lesson = Lesson.objects.create(course=self.course, title='Protected video', order=1, module_id=module['id'], video='learning/videos/private.mp4')
        self.course.status = 'APPROVED'
        self.course.is_free = False
        self.course.save()
        self.client.force_authenticate(self.learner)
        modules = self.client.get(f'/api/learning/courses/{self.course.pk}/modules/')
        self.assertEqual(modules.status_code, 200)
        self.assertEqual([row['id'] for row in modules.data], [module['id']])
        lessons = self.client.get(f'/api/learning/courses/{self.course.pk}/lessons/')
        self.assertEqual(lessons.status_code, 200)
        self.assertEqual(lessons.data[0]['module'], module['id'])
        self.assertIsNone(lessons.data[0]['video'])
        lesson.refresh_from_db()
        self.assertEqual(lesson.video.name, 'learning/videos/private.mp4')

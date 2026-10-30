"""Shared web/API Learning policy and data-preservation regressions."""
from unittest.mock import patch
from unittest import skipUnless
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.auth import get_user_model
from django.test import Client, override_settings
from django.urls import reverse
from django.db import connection, close_old_connections
from rest_framework.test import APIClient, APITestCase, APITransactionTestCase

from .models import Certificate, Course, Enrollment, LearningCategory, Lesson, LessonProgress, Question, Quiz, QuizAttempt
from .services import LearningService
from . import views


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.InMemoryStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class LearningWorkflowRulesTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.creator = User.objects.create_user(username='workflow-creator', role='SCOUT')
        self.learner = User.objects.create_user(username='workflow-learner', role='ATHLETE')
        self.outsider = User.objects.create_user(username='workflow-outsider', role='ATHLETE')
        self.admin = User.objects.create_user(username='workflow-admin', role='ADMIN')
        self.category = LearningCategory.objects.create(name='Workflow fixture')
        self.course = Course.objects.create(creator=self.creator, category=self.category, title='Shared rules',
            slug='shared-rules', description='Preserve this course', status='APPROVED')
        self.lesson = Lesson.objects.create(course=self.course, title='Lesson', order=1)
        self.quiz = Quiz.objects.create(lesson=self.lesson, title='Quiz', passing_score=70)
        self.question = Question.objects.create(quiz=self.quiz, question='Choose A', option_a='A', option_b='B',
            option_c='C', option_d='D', correct_answer='A')
        self.enrollment = Enrollment.objects.create(user=self.learner, course=self.course)
        self.client.force_authenticate(self.learner)
        self.web = Client()
        self.web.force_login(self.learner)
        self.progress_url = f'/api/learning/lessons/{self.lesson.pk}/progress/'
        self.attempt_url = f'/api/learning/quizzes/{self.quiz.pk}/attempt/'
        self.questions_url = f'/api/learning/quizzes/{self.quiz.pk}/questions/'
        self.quiz_url = f'/api/learning/lessons/{self.lesson.pk}/quiz/'

    def pass_quiz(self):
        response = self.client.post(self.attempt_url, {'answers': {str(self.question.pk): 'A'}}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data['passed'])

    def test_quiz_reads_require_scope_and_do_not_leak_answer_key(self):
        self.client.force_authenticate(self.outsider)
        for url in [self.quiz_url, self.questions_url]:
            self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(self.attempt_url, {'answers': {}}, format='json').status_code, 404)
        self.client.force_authenticate(self.learner)
        self.assertEqual(self.client.get(self.quiz_url).status_code, 200)
        data = self.client.get(self.questions_url).data
        self.assertNotIn('correct_answer', data[0])
        self.assertFalse(QuizAttempt.objects.exists())

    def test_draft_quiz_is_private_even_for_existing_enrollment_but_creator_admin_can_preview(self):
        self.course.status = 'DRAFT'
        self.course.save()
        self.assertEqual(self.client.get(self.questions_url).status_code, 404)
        self.assertEqual(self.web.get(reverse('take_quiz', args=[self.quiz.pk])).status_code, 404)
        for actor in [self.creator, self.admin]:
            self.client.force_authenticate(actor)
            self.assertEqual(self.client.get(self.questions_url).status_code, 200)
            self.assertEqual(self.client.post(self.attempt_url, {'answers': {}}, format='json').status_code, 404)

    def test_anonymous_and_inactive_quiz_access_denied(self):
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.quiz_url).status_code, [401, 403])
        self.learner.is_active = False
        self.learner.save()
        self.client.force_authenticate(self.learner)
        self.assertEqual(self.client.get(self.quiz_url).status_code, 404)

    def test_completion_cannot_bypass_quiz_on_api_or_web(self):
        self.assertEqual(self.client.post(self.progress_url, {'completed': True}, format='json').status_code, 400)
        self.assertEqual(self.web.post(reverse(views.complete_lesson, args=[self.lesson.pk])).status_code, 302)
        self.assertFalse(LessonProgress.objects.filter(enrollment=self.enrollment, completed=True).exists())
        self.assertFalse(Certificate.objects.exists())
        self.assertFalse(Enrollment.objects.get(pk=self.enrollment.pk).completed)

    def test_api_completion_issues_pdf_and_retries_preserve_identity_timestamps_and_bytes(self):
        self.pass_quiz()
        self.assertEqual(self.client.post(self.progress_url, {}, format='json').status_code, 200)
        enrollment = Enrollment.objects.get(pk=self.enrollment.pk)
        certificate = Certificate.objects.get(enrollment=enrollment)
        progress = LessonProgress.objects.get(enrollment=enrollment)
        self.assertTrue(enrollment.completed)
        self.assertIsNotNone(enrollment.completed_at)
        with certificate.pdf.open('rb') as stream:
            original = stream.read()
        self.assertTrue(original.startswith(b'%PDF'))
        with patch('learning.utils.generate_certificate') as writer:
            self.assertEqual(self.client.post(self.progress_url, {'completed': True}, format='json').status_code, 200)
            writer.assert_not_called()
        certificate.refresh_from_db()
        self.assertEqual(Certificate.objects.count(), 1)
        self.assertEqual(Enrollment.objects.get(pk=enrollment.pk).completed_at, enrollment.completed_at)
        self.assertEqual(LessonProgress.objects.get(pk=progress.pk).completed_at, progress.completed_at)
        with certificate.pdf.open('rb') as stream:
            self.assertEqual(stream.read(), original)
        download = self.web.get(reverse('download_certificate', args=[certificate.certificate_id]))
        self.assertEqual(download.status_code, 200)
        # Consume Django's closing iterator so the test client manages the
        # request_finished signal without closing the TestCase transaction.
        self.assertTrue(b''.join(download.streaming_content).startswith(b'%PDF'))

    def test_uncomplete_reconciles_flags_without_deleting_award_or_attempt_history(self):
        self.pass_quiz()
        self.client.post(self.progress_url, {'completed': True}, format='json')
        certificate = Certificate.objects.get(enrollment=self.enrollment)
        self.assertEqual(self.client.post(self.progress_url, {'completed': False}, format='json').status_code, 200)
        self.enrollment.refresh_from_db()
        self.assertFalse(self.enrollment.completed)
        self.assertIsNone(self.enrollment.completed_at)
        self.assertEqual(Certificate.objects.get(pk=certificate.pk).certificate_id, certificate.certificate_id)
        self.assertEqual(QuizAttempt.objects.count(), 1)

    def test_pdf_failure_is_retryable_and_never_rolls_back_valid_progress(self):
        self.pass_quiz()
        with patch('learning.utils.generate_certificate', side_effect=OSError('sensitive-provider-detail')):
            response = self.client.post(self.progress_url, {'completed': True}, format='json')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('sensitive-provider-detail', str(response.data))
        certificate = Certificate.objects.get(enrollment=self.enrollment)
        self.assertTrue(Enrollment.objects.get(pk=self.enrollment.pk).completed)
        self.assertFalse(certificate.pdf)
        self.assertEqual(self.client.post(self.progress_url, {'completed': True}, format='json').status_code, 200)
        certificate.refresh_from_db()
        self.assertTrue(certificate.pdf)
        self.assertEqual(Certificate.objects.count(), 1)

    def test_web_attempt_and_api_completion_share_rules(self):
        self.web.post(reverse('take_quiz', args=[self.quiz.pk]), {f'question_{self.question.pk}': 'A'})
        self.assertEqual(self.client.post(self.progress_url, {'completed': True}, format='json').status_code, 200)
        self.assertTrue(Certificate.objects.filter(enrollment=self.enrollment).exists())

    def test_api_attempt_and_web_completion_issue_the_same_certificate(self):
        self.pass_quiz()
        self.assertEqual(self.web.post(reverse(views.complete_lesson, args=[self.lesson.pk])).status_code, 302)
        certificate = Certificate.objects.get(enrollment=self.enrollment)
        self.assertTrue(certificate.pdf)
        self.assertIsNotNone(Enrollment.objects.get(pk=self.enrollment.pk).completed_at)

    def test_missing_pdf_download_uses_retry_helper_without_changing_identity(self):
        self.pass_quiz()
        with patch('learning.utils.generate_certificate', side_effect=OSError('provider-secret')):
            self.client.post(self.progress_url, {'completed': True}, format='json')
        certificate = Certificate.objects.get(enrollment=self.enrollment)
        url = reverse('download_certificate', args=[certificate.certificate_id])
        with patch('learning.views.generate_certificate', side_effect=OSError('provider-secret')):
            response = self.web.get(url)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b'provider-secret', response.content)
        response = self.web.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(b''.join(response.streaming_content).startswith(b'%PDF'))
        self.assertEqual(Certificate.objects.get(pk=certificate.pk).certificate_id, certificate.certificate_id)

    def test_malformed_quiz_inputs_do_not_create_attempts(self):
        for body in [[], {'answers': []}, {'answers': None}, {'answers': {str(self.question.pk): []}},
                     {'answers': {str(self.question.pk): 'Z'}}, {'answers': {'999999': 'A'}}]:
            with self.subTest(body=body):
                self.assertEqual(self.client.post(self.attempt_url, body, format='json').status_code, 400)
        self.assertFalse(QuizAttempt.objects.exists())
        response = self.web.post(reverse('take_quiz', args=[self.quiz.pk]), {f'question_{self.question.pk}': 'Z'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(QuizAttempt.objects.exists())

    def test_attempt_feedback_is_server_graded_ephemeral_and_history_supports_safe_retry(self):
        failed = self.client.post(self.attempt_url, {'answers': {str(self.question.pk): 'B'}}, format='json')
        self.assertEqual(failed.status_code, 201)
        self.assertFalse(failed.data['passed'])
        self.assertEqual(failed.data['question_feedback'], [{
            'question_id': self.question.pk, 'question': 'Choose A', 'selected_answer': 'B',
            'selected_text': 'B', 'correct_answer': 'A', 'correct_text': 'A', 'is_correct': False,
        }])
        self.assertNotIn('question_feedback', [field.name for field in QuizAttempt._meta.fields])
        history = self.client.get('/api/learning/quiz-attempts/me/')
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.data[0]['lesson_id'], self.lesson.pk)
        self.assertEqual(history.data[0]['passing_score'], 70)
        self.assertFalse(history.data[0]['passed'])
        self.assertEqual(self.client.post(self.progress_url, {'completed': True}, format='json').status_code, 400)
        self.assertFalse(Certificate.objects.exists())

        passed = self.client.post(self.attempt_url, {'answers': {str(self.question.pk): 'A'}}, format='json')
        self.assertTrue(passed.data['passed'])
        self.assertTrue(passed.data['question_feedback'][0]['is_correct'])
        self.assertNotIn('correct_answer', self.client.get(self.questions_url).data[0])
        history = self.client.get('/api/learning/quiz-attempts/me/')
        self.assertEqual(len(history.data), 2)
        self.assertTrue(history.data[0]['passed'])
        self.assertEqual(QuizAttempt.objects.count(), 2)

    def test_malformed_completion_and_missing_enrollment_do_not_write_progress(self):
        for body in [[], {'completed': []}, {'completed': {}}, {'completed': 'maybe'}, {'completed': None}]:
            with self.subTest(body=body):
                self.assertEqual(self.client.post(self.progress_url, body, format='json').status_code, 400)
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.post(self.progress_url, {'completed': True}, format='json').status_code, 404)
        self.assertFalse(LessonProgress.objects.exists())

    def test_empty_quiz_cannot_be_passed_or_completed_with_legacy_attempt(self):
        self.question.delete()
        self.assertEqual(self.client.post(self.attempt_url, {'answers': {}}, format='json').status_code, 400)
        QuizAttempt.objects.create(enrollment=self.enrollment, quiz=self.quiz, passed=True)
        self.assertEqual(self.client.post(self.progress_url, {'completed': True}, format='json').status_code, 400)

    def test_paid_enrollment_is_blocked_on_web_and_api_without_removing_existing_enrollment(self):
        self.course.is_free = False
        self.course.save()
        self.client.force_authenticate(self.outsider)
        self.web.force_login(self.outsider)
        self.assertEqual(self.client.post(f'/api/learning/courses/{self.course.pk}/enroll/').status_code, 402)
        self.assertEqual(self.web.post(reverse('enroll_course', args=[self.course.pk])).status_code, 302)
        self.assertFalse(Enrollment.objects.filter(user=self.outsider, course=self.course).exists())
        self.assertTrue(Enrollment.objects.filter(pk=self.enrollment.pk).exists())

    def test_existing_paid_enrollment_keeps_learning_and_certificate_access(self):
        self.course.is_free = False
        self.course.save()
        self.pass_quiz()
        self.assertEqual(self.client.post(self.progress_url, {'completed': True}, format='json').status_code, 200)
        self.assertTrue(Certificate.objects.get(enrollment=self.enrollment).pdf)

    def test_legacy_award_bytes_identity_and_completion_time_survive_retry(self):
        from datetime import timedelta
        from django.core.files.base import ContentFile
        from django.utils import timezone
        self.pass_quiz()
        original_time = timezone.now() - timedelta(days=30)
        self.enrollment.completed = True
        self.enrollment.completed_at = original_time
        self.enrollment.save()
        LessonProgress.objects.create(enrollment=self.enrollment, lesson=self.lesson, completed=True, completed_at=original_time)
        award = Certificate.objects.create(enrollment=self.enrollment, certificate_id='LEGACY-UNCHANGED')
        award.pdf.save('legacy.pdf', ContentFile(b'%PDF-preserved-fixture'))
        original_name = award.pdf.name
        with patch('learning.utils.generate_certificate') as writer:
            self.assertEqual(self.client.post(self.progress_url, {}, format='json').status_code, 200)
            writer.assert_not_called()
        award.refresh_from_db()
        self.assertEqual((award.certificate_id, award.pdf.name), ('LEGACY-UNCHANGED', original_name))
        self.assertEqual(Enrollment.objects.get(pk=self.enrollment.pk).completed_at, original_time)
        with award.pdf.open('rb') as stream:
            self.assertEqual(stream.read(), b'%PDF-preserved-fixture')

    def test_free_enrollment_remains_unique_and_web_csrf_is_required(self):
        self.client.force_authenticate(self.outsider)
        url = f'/api/learning/courses/{self.course.pk}/enroll/'
        self.assertEqual(self.client.post(url).status_code, 201)
        self.assertEqual(self.client.post(url).status_code, 400)
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.learner)
        self.assertEqual(browser.post(reverse('enroll_course', args=[self.course.pk])).status_code, 403)
        self.assertEqual(browser.post(reverse(views.complete_lesson, args=[self.lesson.pk])).status_code, 403)
        self.assertEqual(Enrollment.objects.filter(user=self.outsider, course=self.course).count(), 1)

    def test_all_creator_roles_can_create_on_api_and_web(self):
        for role in LearningService.ALLOWED_CREATOR_ROLES:
            user = get_user_model().objects.create_user(username='creator-' + role, role=role)
            self.client.force_authenticate(user)
            self.web.force_login(user)
            self.assertEqual(self.web.get(reverse('create_course')).status_code, 200)
            response = self.client.post('/api/learning/courses/create/', {'title': role, 'slug': role.lower(),
                'description': 'Valid', 'category': self.category.pk}, format='json')
            self.assertEqual(response.status_code, 201, response.data)

    def test_readiness_is_shared_by_submit_and_approval_without_changing_existing_courses(self):
        empty = Course.objects.create(creator=self.creator, category=self.category, title='Empty', slug='empty',
            description='Preserve', status='REJECTED', rejection_reason='Original reason')
        self.client.force_authenticate(self.creator)
        self.web.force_login(self.creator)
        self.assertEqual(self.client.post(f'/api/learning/courses/{empty.pk}/submit/').status_code, 400)
        self.assertEqual(self.web.post(reverse('submit_course', args=[empty.pk])).status_code, 302)
        empty.refresh_from_db()
        self.assertEqual((empty.status, empty.rejection_reason), ('REJECTED', 'Original reason'))
        lesson = Lesson.objects.create(course=empty, title='Ready', order=1)
        Quiz.objects.create(lesson=lesson, title='Unfinished')
        self.assertEqual(self.client.post(f'/api/learning/courses/{empty.pk}/submit/').status_code, 400)
        empty.status = 'PENDING'
        empty.save()
        self.client.force_authenticate(self.admin)
        self.web.force_login(self.admin)
        self.assertEqual(self.client.post(f'/api/learning/courses/{empty.pk}/approve/').status_code, 400)
        self.assertEqual(self.web.post(reverse('approve_course', args=[empty.pk])).status_code, 302)
        self.assertEqual(Course.objects.get(pk=empty.pk).status, 'PENDING')
        self.assertEqual(Course.objects.get(pk=self.course.pk).status, 'APPROVED')

    def test_completed_course_needs_every_lesson_and_required_quiz(self):
        another = Lesson.objects.create(course=self.course, title='Second', order=2)
        self.pass_quiz()
        self.assertEqual(self.client.post(self.progress_url, {'completed': True}, format='json').status_code, 200)
        self.assertFalse(Certificate.objects.exists())
        self.assertEqual(self.client.post(f'/api/learning/lessons/{another.pk}/progress/', {}, format='json').status_code, 200)
        self.assertEqual(Certificate.objects.count(), 1)

    def test_stale_admin_role_and_revoked_enrollment_cannot_read_quiz(self):
        get_user_model().objects.filter(pk=self.admin.pk).update(role='ATHLETE')
        self.client.force_authenticate(self.admin)  # Deliberately stale role object.
        self.assertEqual(self.client.get(self.questions_url).status_code, 404)
        self.enrollment.delete()
        self.client.force_authenticate(self.learner)
        self.assertEqual(self.client.get(self.quiz_url).status_code, 404)

    def test_quiz_authoring_and_rejection_inputs_are_validated_server_side(self):
        from .forms import QuizForm, QuestionForm
        for score in [-1, 0, 101, 'not-a-number']:
            self.assertFalse(QuizForm(data={'title': 'Quiz', 'passing_score': score}).is_valid())
        invalid_question = {'question': 'Q', 'option_a': 'A', 'option_b': 'B', 'option_c': 'C', 'option_d': 'D', 'correct_answer': 'Z'}
        self.assertFalse(QuestionForm(data=invalid_question).is_valid())
        self.course.status = 'PENDING'
        self.course.save()
        self.client.force_authenticate(self.admin)
        for value in [[], {}, None, 123, True]:
            response = self.client.post(f'/api/learning/courses/{self.course.pk}/reject/', {'rejection_reason': value}, format='json')
            self.assertEqual(response.status_code, 400)
        self.assertEqual(Course.objects.get(pk=self.course.pk).status, 'PENDING')

    def test_creator_studio_authoring_uses_owner_and_moderation_guards(self):
        self.course.status = 'DRAFT'
        self.course.save(update_fields=['status'])
        readiness = f'/api/learning/courses/{self.course.pk}/readiness/'
        quiz_status = f'/api/learning/studio/lessons/{self.lesson.pk}/quiz/'
        question_list = f'/api/learning/studio/quizzes/{self.quiz.pk}/questions/'
        self.client.force_authenticate(self.creator)
        self.assertTrue(self.client.get(readiness).data['ready'])
        self.assertEqual(self.client.get(quiz_status).data['quiz']['id'], self.quiz.pk)
        self.assertEqual(self.client.get(question_list).data[0]['correct_answer'], 'A')
        updated = self.client.patch(f'/api/learning/lessons/{self.lesson.pk}/',
            {'title': 'Updated lesson', 'order': 2}, format='json')
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual((updated.data['title'], updated.data['order']), ('Updated lesson', 2))
        question = self.client.patch(f'/api/learning/studio/questions/{self.question.pk}/',
            {'question': 'Updated prompt'}, format='json')
        self.assertEqual(question.status_code, 200, question.data)
        self.assertEqual(QuizAttempt.objects.count(), 0)
        added = self.client.post(question_list, {'question': 'Choose B', 'option_a': 'A', 'option_b': 'B',
            'option_c': 'C', 'option_d': 'D', 'correct_answer': 'B'}, format='json')
        self.assertEqual(added.status_code, 201, added.data)
        self.assertEqual(added.data['correct_answer'], 'B')
        self.assertEqual(self.client.post(quiz_status, {'title': 'Duplicate'} , format='json').status_code, 409)

        self.client.force_authenticate(self.learner)
        self.assertEqual(self.client.get(readiness).status_code, 403)
        self.assertEqual(self.client.get(quiz_status).status_code, 403)
        self.assertEqual(self.client.get(question_list).status_code, 403)
        self.assertEqual(self.client.patch(f'/api/learning/lessons/{self.lesson.pk}/', {'title': 'Forbidden'}, format='json').status_code, 403)
        self.client.force_authenticate(self.creator)
        self.course.status = 'PENDING'
        self.course.save(update_fields=['status'])
        self.assertEqual(self.client.patch(f'/api/learning/lessons/{self.lesson.pk}/', {'title': 'Locked'}, format='json').status_code, 400)
        self.assertEqual(self.client.post(question_list, {'question': 'Blocked', 'option_a': 'A', 'option_b': 'B',
            'option_c': 'C', 'option_d': 'D', 'correct_answer': 'A'}, format='json').status_code, 400)
        self.assertEqual(Question.objects.filter(quiz=self.quiz).count(), 2)

    def test_creator_preview_is_owner_scoped_and_never_creates_learner_history(self):
        self.course.status = 'DRAFT'
        self.course.save(update_fields=['status'])
        self.client.force_authenticate(self.creator)
        self.assertContains(self.client.get(f'/api/learning/courses/{self.course.pk}/'), 'DRAFT')
        self.assertEqual(self.client.get(f'/api/learning/lessons/{self.lesson.pk}/').status_code, 200)
        self.assertEqual(LessonProgress.objects.count(), 0)
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(f'/api/learning/courses/{self.course.pk}/').status_code, 404)
        self.assertEqual(self.client.get(f'/api/learning/courses/{self.course.pk}/lessons/').status_code, 404)


@skipUnless(connection.vendor == 'postgresql', 'Real enrollment row-lock concurrency')
@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.InMemoryStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class LearningCompletionConcurrencyTests(APITransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='completion-race', role='ATHLETE')
        category = LearningCategory.objects.create(name='Concurrent completion')
        course = Course.objects.create(creator=self.user, category=category, title='Concurrent', slug='concurrent',
            description='Synthetic', status='APPROVED')
        self.lesson = Lesson.objects.create(course=course, title='First', order=1)
        self.enrollment = Enrollment.objects.create(user=self.user, course=course)

    def race(self, lessons):
        barrier = Barrier(2)

        def complete(lesson):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                progress, certificate = LearningService.set_lesson_completion(lesson, self.user)
                LearningService.ensure_certificate_pdf(certificate)
                return progress.pk
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(complete, lesson) for lesson in lessons]
            return [future.result(timeout=30) for future in futures]

    def test_concurrent_duplicate_completion_creates_one_award_and_pdf(self):
        from .utils import generate_certificate
        with patch('learning.utils.generate_certificate', wraps=generate_certificate) as writer:
            ids = self.race([self.lesson, self.lesson])
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(writer.call_count, 1)
        self.assertEqual(Certificate.objects.count(), 1)
        self.assertTrue(Certificate.objects.get().pdf)

    def test_concurrent_last_lessons_cannot_leave_completion_stale(self):
        second = Lesson.objects.create(course=self.lesson.course, title='Second', order=2)
        self.race([self.lesson, second])
        self.enrollment.refresh_from_db()
        self.assertTrue(self.enrollment.completed)
        self.assertIsNotNone(self.enrollment.completed_at)
        self.assertEqual(LessonProgress.objects.filter(completed=True).count(), 2)
        self.assertEqual(Certificate.objects.count(), 1)

    def test_concurrent_mobile_lesson_appends_have_distinct_server_orders(self):
        course = self.lesson.course
        course.status = 'DRAFT'
        course.save()
        self.lesson.order = 90
        self.lesson.save()
        barrier = Barrier(2)

        def append(title):
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(self.user)
                barrier.wait(timeout=10)
                response = client.post(f'/api/learning/courses/{course.pk}/lessons/create/',
                    {'title': title, 'order': 2}, format='json')
                self.assertEqual(response.status_code, 201, response.data)
                return response.data['order']
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(append, title) for title in ['Concurrent A', 'Concurrent B']]
            self.assertEqual(sorted(f.result(timeout=30) for f in futures), [91, 92])
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.order, 90)

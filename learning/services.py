from django.utils import timezone
from django.db import transaction
from django.http import Http404

from .models import (
    Course,
    Enrollment,
    Certificate,
    QuizAttempt,
    LessonProgress,
    Quiz,
)


class LearningService:
    """
    Business logic for the Awinlink Learning system.
    """

    ALLOWED_CREATOR_ROLES = {
        "ATHLETE",
        "ORGANIZATION",
        "SCOUT",
        "COACH",
        "ADMIN",
    }

    @staticmethod
    def can_read_quiz(user, course):
        if not user.is_authenticated or not user.is_active:
            return False
        from django.contrib.auth import get_user_model
        actor = get_user_model().objects.filter(pk=user.pk, is_active=True).values('role').first()
        if actor is None:
            return False
        if course.creator_id == user.pk or actor['role'] == 'ADMIN':
            return True
        return course.status == 'APPROVED' and Enrollment.objects.filter(user=user, course=course).exists()

    @staticmethod
    def require_quiz_access(user, course):
        if not LearningService.can_read_quiz(user, course):
            raise Http404('Quiz is not available.')

    @staticmethod
    def submission_checklist(course):
        lessons = list(course.lessons.all().order_by('order', 'pk'))
        quizzes = list(Quiz.objects.filter(lesson__course=course).prefetch_related('questions'))
        quiz_issues = []
        if any(not quiz.questions.all() or not 0 <= quiz.passing_score <= 100 for quiz in quizzes):
            quiz_issues.append('Each quiz needs questions and a passing score between 0 and 100.')
        elif any(
            question.correct_answer not in {'A', 'B', 'C', 'D'} or not question.question.strip()
            or any(not getattr(question, 'option_' + letter).strip() for letter in 'abcd')
            for quiz in quizzes for question in quiz.questions.all()
        ):
            quiz_issues.append('Complete each quiz question and select a valid correct answer.')

        course_ready = bool(course.category_id and (course.title or '').strip() and (course.description or '').strip())
        curriculum_ready = bool(lessons)
        quiz_ready = not quiz_issues
        return [
            {'key': 'course', 'label': 'Course information', 'ready': course_ready,
             'detail': 'Title, category and description are ready.' if course_ready else 'Add a title, category and description.'},
            {'key': 'curriculum', 'label': 'Lesson curriculum', 'ready': curriculum_ready,
             'detail': f'{len(lessons)} lesson(s) added.' if curriculum_ready else 'Add at least one lesson before submitting.'},
            {'key': 'quizzes', 'label': 'Quiz content', 'ready': quiz_ready,
             'detail': quiz_issues[0] if quiz_issues else ('Quizzes are optional; included quizzes are complete.' if quizzes else 'Quizzes are optional.')},
        ]

    @staticmethod
    def validate_submission(course):
        checklist = LearningService.submission_checklist(course)
        course_info = next(item for item in checklist if item['key'] == 'course')
        curriculum = next(item for item in checklist if item['key'] == 'curriculum')
        quiz_content = next(item for item in checklist if item['key'] == 'quizzes')
        if not course_info['ready']:
            raise ValueError('Complete the course title, category and description before submitting.')
        if not curriculum['ready']:
            raise ValueError('Add at least one lesson before submitting the course.')
        if not quiz_content['ready']:
            raise ValueError(quiz_content['detail'])

    @staticmethod
    @transaction.atomic
    def enroll(course, user):
        course = Course.objects.select_for_update().get(pk=course.pk)
        if not user.is_authenticated or not user.is_active or course.status != 'APPROVED':
            raise Http404('Course is not available.')
        if not course.is_free:
            raise ValueError('Paid enrollment is unavailable until store billing is configured.')
        return Enrollment.objects.get_or_create(user=user, course=course)

    @staticmethod
    @transaction.atomic
    def set_lesson_completion(lesson, user, completed=True):
        if type(completed) is not bool:
            raise ValueError('completed must be a boolean.')
        LearningService.require_quiz_access(user, lesson.course)
        try:
            enrollment = Enrollment.objects.select_for_update(of=('self',)).select_related('course', 'user').get(user=user, course=lesson.course)
        except Enrollment.DoesNotExist:
            raise Http404('Enrollment is required.') from None
        quiz = Quiz.objects.filter(lesson=lesson).first()
        if completed and quiz:
            LearningService.evaluate_quiz(quiz, {})  # Reject an empty/invalid quiz even with legacy attempts.
            if not QuizAttempt.objects.filter(enrollment=enrollment, quiz=quiz, passed=True).exists():
                raise ValueError('You must pass the quiz for this lesson before completing it.')
        progress, _ = LessonProgress.objects.get_or_create(enrollment=enrollment, lesson=lesson)
        if progress.completed != completed:
            progress.completed = completed
            progress.completed_at = timezone.now() if completed else None
            progress.save(update_fields=['completed', 'completed_at'])
        certificate = LearningService.update_course_completion(enrollment)
        return progress, certificate

    @staticmethod
    def ensure_certificate_pdf(certificate, writer=None):
        if certificate is None or certificate.pdf:
            return certificate
        # Progress/certificate identity are committed before external storage.
        # Retrying completion retries a missing PDF without replacing old files.
        if writer is None:
            from .utils import generate_certificate
            writer = generate_certificate
        with transaction.atomic():
            locked = Certificate.objects.select_for_update(of=('self',)).select_related('enrollment__course', 'enrollment__user').get(pk=certificate.pk)
            return locked if locked.pdf else writer(locked.enrollment)

    @staticmethod
    @transaction.atomic
    def record_quiz_attempt(quiz, user, answers):
        LearningService.require_quiz_access(user, quiz.lesson.course)
        try:
            enrollment = Enrollment.objects.select_for_update().get(user=user, course=quiz.lesson.course)
        except Enrollment.DoesNotExist:
            raise Http404('Enrollment is required.') from None
        result = LearningService.evaluate_quiz(quiz, answers)
        attempt = QuizAttempt.objects.create(enrollment=enrollment, quiz=quiz, **result)
        # Keep answer review ephemeral. Historical attempts predate answer
        # storage, and grading remains exclusively server-side.
        feedback = []
        for question in quiz.questions.all().order_by('id'):
            selected = answers.get(str(question.pk))
            correct = question.correct_answer.strip().upper()
            selected_text = getattr(question, f'option_{selected.lower()}', None) if selected else None
            feedback.append({
                'question_id': question.pk, 'question': question.question,
                'selected_answer': selected, 'selected_text': selected_text,
                'correct_answer': correct, 'correct_text': getattr(question, f'option_{correct.lower()}'),
                'is_correct': selected == correct,
            })
        attempt.question_feedback = feedback
        return attempt

    @staticmethod
    def can_create_course(user):
        """
        Check whether a user is allowed to create
        learning courses.
        """
        return (
            user.is_authenticated
            and getattr(user, 'is_active', True)
            and user.role in LearningService.ALLOWED_CREATOR_ROLES
        )

    @staticmethod
    @transaction.atomic
    def submit_course(course, user):
        """
        Submit a draft course for admin review.
        """

        course = Course.objects.select_for_update().get(pk=course.pk)
        if course.creator != user or not LearningService.can_create_course(user):
            raise PermissionError(
                "Only the course creator can submit this course."
            )

        if course.status not in {"DRAFT", "REJECTED"}:
            raise ValueError(
                "Only draft or rejected courses can be submitted."
            )

        if not course.is_free:
            raise ValueError("Paid courses cannot be submitted until Learning billing is available.")

        LearningService.validate_submission(course)
        course.status = "PENDING"
        course.rejection_reason = ""
        course.save(
            update_fields=[
                "status",
                "rejection_reason",
                "updated_at",
            ]
        )

        return course

    @staticmethod
    @transaction.atomic
    def approve_course(course):
        """
        Approve a course that is awaiting review.
        """

        course = Course.objects.select_for_update().get(pk=course.pk)
        if course.status != "PENDING":
            raise ValueError(
                "Only pending courses can be approved."
            )

        if not course.is_free:
            raise ValueError("Paid courses cannot be published until Learning billing is available.")

        LearningService.validate_submission(course)
        course.status = "APPROVED"
        course.rejection_reason = ""

        course.save(
            update_fields=[
                "status",
                "rejection_reason",
                "updated_at",
            ]
        )

        return course

    @staticmethod
    @transaction.atomic
    def reject_course(course, reason):
        """
        Reject a course and record the reason.
        """

        course = Course.objects.select_for_update().get(pk=course.pk)
        if course.status != "PENDING":
            raise ValueError(
                "Only pending courses can be rejected."
            )

        if not isinstance(reason, str):
            raise ValueError('A rejection reason must be text.')
        reason = reason.strip()

        if not reason:
            raise ValueError(
                "A rejection reason is required."
            )

        course.status = "REJECTED"
        course.rejection_reason = reason

        course.save(
            update_fields=[
                "status",
                "rejection_reason",
                "updated_at",
            ]
        )

        return course

    @staticmethod
    @transaction.atomic
    def complete_enrollment(enrollment):
        """
        Mark an enrollment as completed and create
        its certificate if one does not already exist.
        """

        enrollment = Enrollment.objects.select_for_update(of=('self',)).select_related('course').get(pk=enrollment.pk)
        if not LearningService.calculate_course_completion(enrollment):
            raise ValueError('Complete all lessons and required quizzes before issuing a certificate.')
        if enrollment.completed:
            if enrollment.completed_at is None:
                enrollment.completed_at = timezone.now()
                enrollment.save(update_fields=['completed_at'])
            certificate, _ = Certificate.objects.get_or_create(
                enrollment=enrollment, defaults={'certificate_id': LearningService.generate_certificate_id()}
            )

            if not certificate.certificate_id:
                certificate.certificate_id = (
                    LearningService.generate_certificate_id()
                )
                certificate.save(
                    update_fields=["certificate_id"]
                )

            return certificate

        enrollment.completed = True
        enrollment.completed_at = timezone.now()

        enrollment.save(
            update_fields=[
                "completed",
                "completed_at",
            ]
        )

        certificate, created = Certificate.objects.get_or_create(
            enrollment=enrollment,
            defaults={
                "certificate_id":
                    LearningService.generate_certificate_id()
            }
        )

        if not created and not certificate.certificate_id:
            certificate.certificate_id = (
                LearningService.generate_certificate_id()
            )
            certificate.save(
                update_fields=["certificate_id"]
            )

        return certificate

    @staticmethod
    def generate_certificate_id():
        """
        Generate a unique certificate identifier.
        """

        import uuid

        while True:
            certificate_id = (
                f"AWL-{uuid.uuid4().hex[:10].upper()}"
            )

            if not Certificate.objects.filter(
                certificate_id=certificate_id
            ).exists():
                return certificate_id

    @staticmethod
    def calculate_course_completion(enrollment):
        """
        Determine whether all lessons in a course
        have been completed.
        """

        total_lessons = enrollment.course.lessons.count()

        if total_lessons == 0:
            return False

        completed_lessons = enrollment.lesson_progress.filter(
            completed=True, lesson__course=enrollment.course
        ).count()

        quizzes = Quiz.objects.filter(lesson__course=enrollment.course)
        passed = QuizAttempt.objects.filter(enrollment=enrollment, quiz__in=quizzes, passed=True).values('quiz_id').distinct().count()
        return completed_lessons >= total_lessons and passed == quizzes.count()

    @staticmethod
    def update_course_completion(enrollment):
        """
        Recalculate course completion based on
        current lesson progress.
        """

        is_complete = (
            LearningService.calculate_course_completion(
                enrollment
            )
        )

        if is_complete:
            return LearningService.complete_enrollment(
                enrollment
            )

        enrollment.completed = False
        enrollment.completed_at = None
        enrollment.save(
            update_fields=[
                "completed",
                "completed_at",
            ]
        )

        return None

    @staticmethod
    def evaluate_quiz(quiz, answers):
        """
        Evaluate submitted quiz answers on the server.
        """

        questions = list(quiz.questions.all())

        total_questions = len(questions)
        score = 0

        if not questions or not 0 <= quiz.passing_score <= 100:
            raise ValueError('This quiz is not ready for attempts.')
        if not isinstance(answers, dict):
            raise ValueError('answers must be an object keyed by question ID.')
        ids = {str(question.pk) for question in questions}
        if any(key not in ids or not isinstance(value, str) or value not in {'A', 'B', 'C', 'D'} for key, value in answers.items()):
            raise ValueError('Answers must use this quiz\'s question IDs and choices A, B, C or D.')
        if any(question.correct_answer not in {'A', 'B', 'C', 'D'} for question in questions):
            raise ValueError('This quiz is not ready for attempts.')

        for question in questions:
            submitted_answer = answers.get(
                str(question.id)
            )

            if submitted_answer:
                submitted_answer = str(
                    submitted_answer
                ).strip().upper()

            correct_answer = str(
                question.correct_answer
            ).strip().upper()

            if submitted_answer == correct_answer:
                score += 1

        if total_questions:
            percentage = round(
                (score / total_questions) * 100
            )
        else:
            percentage = 0

        passed = (
            percentage >= quiz.passing_score
        )

        return {
            "score": score,
            "total_questions": total_questions,
            "percentage": percentage,
            "passed": passed,
        }

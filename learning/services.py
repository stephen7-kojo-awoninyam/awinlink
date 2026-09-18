from django.utils import timezone

from .models import (
    Course,
    Enrollment,
    Certificate,
    QuizAttempt,
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
    def can_create_course(user):
        """
        Check whether a user is allowed to create
        learning courses.
        """
        return (
            user.is_authenticated
            and user.role in LearningService.ALLOWED_CREATOR_ROLES
        )

    @staticmethod
    def submit_course(course, user):
        """
        Submit a draft course for admin review.
        """

        if course.creator != user:
            raise PermissionError(
                "Only the course creator can submit this course."
            )

        if course.status != "DRAFT":
            raise ValueError(
                "Only draft courses can be submitted."
            )

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
    def approve_course(course):
        """
        Approve a course that is awaiting review.
        """

        if course.status != "PENDING":
            raise ValueError(
                "Only pending courses can be approved."
            )

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
    def reject_course(course, reason):
        """
        Reject a course and record the reason.
        """

        if course.status != "PENDING":
            raise ValueError(
                "Only pending courses can be rejected."
            )

        reason = (reason or "").strip()

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
    def complete_enrollment(enrollment):
        """
        Mark an enrollment as completed and create
        its certificate if one does not already exist.
        """

        if enrollment.completed:
            certificate, _ = Certificate.objects.get_or_create(
                enrollment=enrollment
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
            completed=True
        ).count()

        return completed_lessons >= total_lessons

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

        questions = quiz.questions.all()

        total_questions = questions.count()
        score = 0

        answers = answers or {}

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
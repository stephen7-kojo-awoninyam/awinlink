from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .services import LearningService
from .models import (
    LearningCategory,
    Course,
    CourseReview,
    Certificate,
    Lesson,
    Enrollment,
    LessonProgress,
    Quiz,
    Question,
    QuizAttempt,
)

from .serializers import (
    LearningCategorySerializer,
    CourseSerializer,
    CourseCreateSerializer,
    CourseReviewSerializer,
    CertificateSerializer,
    LessonSerializer,
    EnrollmentSerializer,
    LessonProgressSerializer,
    QuizSerializer,
    QuestionSerializer,
    QuizAttemptSerializer,
)


# ============================================================
# LEARNING CATEGORIES
# ============================================================

class LearningCategoryListAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        categories = LearningCategory.objects.all()

        serializer = LearningCategorySerializer(
            categories,
            many=True
        )

        return Response(serializer.data)


# ============================================================
# COURSES
# ============================================================

class CourseListAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        courses = Course.objects.filter(
            status="APPROVED"
        ).select_related(
            "creator",
            "category"
        )

        serializer = CourseSerializer(
            courses,
            many=True
        )

        return Response(serializer.data)


# ============================================================
# COURSE DETAIL
# ============================================================

class CourseDetailAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, course_id):

        course = get_object_or_404(
            Course,
            id=course_id
        )

        # Public API users should only see approved courses.
        # Creators and admins can see their own/unapproved courses.

        if (
            course.status != "APPROVED"
            and course.creator != request.user
            and request.user.role != "ADMIN"
        ):
            return Response(
                {
                    "detail": "This course is not available."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = CourseSerializer(course)

        return Response(serializer.data)


# ============================================================
# CREATE COURSE
# ============================================================

class CourseCreateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        allowed_roles = [
             "ATHLETE",
            "ORGANIZATION",
            "COACH",
            "ADMIN",
        ]

        if request.user.role not in allowed_roles:

            return Response(
                {
                    "detail": (
                        "You do not have permission "
                        "to create courses."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = CourseCreateSerializer(
            data=request.data
        )

        if serializer.is_valid():

            course = serializer.save(
                creator=request.user
            )

            response_serializer = CourseSerializer(
                course
            )

            return Response(
                response_serializer.data,
                status=status.HTTP_201_CREATED
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


# ============================================================
# MY COURSES
# ============================================================

class MyCoursesAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        courses = Course.objects.filter(
            creator=request.user
        ).select_related(
            "category"
        )

        serializer = CourseSerializer(
            courses,
            many=True
        )

        return Response(serializer.data)

# ============================================================
# SUBMIT COURSE FOR REVIEW
# ============================================================

class CourseSubmitAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, course_id):

        course = get_object_or_404(
            Course,
            id=course_id
        )

        try:
            course = LearningService.submit_course(
                course=course,
                user=request.user
            )

        except PermissionError as error:
            return Response(
                {
                    "detail": str(error)
                },
                status=status.HTTP_403_FORBIDDEN
            )

        except ValueError as error:
            return Response(
                {
                    "detail": str(error)
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            CourseSerializer(course).data,
            status=status.HTTP_200_OK
        )
        
# ============================================================
# APPROVE COURSE
# ============================================================

class CourseApproveAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, course_id):

        if request.user.role != "ADMIN":
            return Response(
                {
                    "detail": (
                        "Only ADMIN users can approve courses."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        course = get_object_or_404(
            Course,
            id=course_id
        )

        try:
            course = LearningService.approve_course(
                course
            )

        except ValueError as error:
            return Response(
                {
                    "detail": str(error)
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            CourseSerializer(course).data,
            status=status.HTTP_200_OK
        )
        
# ============================================================
# REJECT COURSE
# ============================================================

class CourseRejectAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, course_id):

        if request.user.role != "ADMIN":
            return Response(
                {
                    "detail": (
                        "Only ADMIN users can reject courses."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        course = get_object_or_404(
            Course,
            id=course_id
        )

        reason = request.data.get(
            "rejection_reason",
            ""
        )

        try:
            course = LearningService.reject_course(
                course=course,
                reason=reason
            )

        except ValueError as error:
            return Response(
                {
                    "detail": str(error)
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            CourseSerializer(course).data,
            status=status.HTTP_200_OK
        )                
# ============================================================
# LESSONS FOR COURSE
# ============================================================

class CourseLessonsAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, course_id):

        course = get_object_or_404(
            Course,
            id=course_id
        )

        if (
            course.status != "APPROVED"
            and course.creator != request.user
            and request.user.role != "ADMIN"
        ):
            return Response(
                {
                    "detail": "This course is not available."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        lessons = course.lessons.all()

        serializer = LessonSerializer(
            lessons,
            many=True
        )

        return Response(serializer.data)


# ============================================================
# CREATE LESSON
# ============================================================

class LessonCreateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, course_id):

        course = get_object_or_404(
            Course,
            id=course_id
        )

        if course.creator != request.user:

            return Response(
                {
                    "detail": (
                        "Only the course creator "
                        "can add lessons."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        if course.status in [
            "PENDING",
            "APPROVED",
        ]:

            return Response(
                {
                    "detail": (
                        "Lessons cannot be modified "
                        "while the course is pending "
                        "or approved."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = LessonSerializer(
            data={
                **request.data,
                "course": course.id
            }
        )

        if serializer.is_valid():

            lesson = serializer.save()

            return Response(
                LessonSerializer(lesson).data,
                status=status.HTTP_201_CREATED
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


# ============================================================
# LESSON DETAIL
# ============================================================

class LessonDetailAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, lesson_id):

        lesson = get_object_or_404(
            Lesson,
            id=lesson_id
        )

        course = lesson.course

        if (
            course.status != "APPROVED"
            and course.creator != request.user
            and request.user.role != "ADMIN"
        ):
            return Response(
                {
                    "detail": "Lesson is not available."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = LessonSerializer(
            lesson
        )

        return Response(serializer.data)


# ============================================================
# ENROLL IN COURSE
# ============================================================

class CourseEnrollmentAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, course_id):

        course = get_object_or_404(
            Course,
            id=course_id,
            status="APPROVED"
        )

        if Enrollment.objects.filter(
            user=request.user,
            course=course
        ).exists():

            return Response(
                {
                    "detail": "You are already enrolled."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        enrollment = Enrollment.objects.create(
            user=request.user,
            course=course
        )

        serializer = EnrollmentSerializer(
            enrollment
        )

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED
        )


# ============================================================
# MY ENROLLMENTS
# ============================================================

class MyEnrollmentsAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        enrollments = Enrollment.objects.filter(
            user=request.user
        ).select_related(
            "course"
        )

        serializer = EnrollmentSerializer(
            enrollments,
            many=True
        )

        return Response(serializer.data)


# ============================================================
# LESSON PROGRESS
# ============================================================

class LessonProgressAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, lesson_id):

        lesson = get_object_or_404(
            Lesson,
            id=lesson_id
        )

        enrollment = get_object_or_404(
            Enrollment,
            user=request.user,
            course=lesson.course
        )

        progress, created = LessonProgress.objects.get_or_create(
            enrollment=enrollment,
            lesson=lesson
        )

        completed = request.data.get(
            "completed",
            True
        )

        progress.completed = completed

        if completed:
            progress.completed_at = timezone.now()
        else:
            progress.completed_at = None

        progress.save()

        # Check whether all lessons are completed.
        total_lessons = lesson.course.lessons.count()

        completed_lessons = LessonProgress.objects.filter(
            enrollment=enrollment,
            completed=True
        ).count()

        if (
            total_lessons > 0
            and completed_lessons >= total_lessons
        ):
            enrollment.completed = True
            enrollment.completed_at = timezone.now()
            enrollment.save(
                update_fields=[
                    "completed",
                    "completed_at"
                ]
            )

        serializer = LessonProgressSerializer(
            progress
        )

        return Response(serializer.data)


# ============================================================
# COURSE PROGRESS
# ============================================================

class CourseProgressAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, course_id):

        course = get_object_or_404(
            Course,
            id=course_id
        )

        enrollment = get_object_or_404(
            Enrollment,
            user=request.user,
            course=course
        )

        total_lessons = course.lessons.count()

        completed_lessons = LessonProgress.objects.filter(
            enrollment=enrollment,
            completed=True
        ).count()

        if total_lessons > 0:

            percentage = round(
                (
                    completed_lessons
                    / total_lessons
                ) * 100
            )

        else:

            percentage = 0

        return Response(
            {
                "course": course.id,
                "course_title": course.title,
                "enrollment": enrollment.id,
                "total_lessons": total_lessons,
                "completed_lessons": completed_lessons,
                "progress_percentage": percentage,
                "completed": enrollment.completed,
            }
        )


# ============================================================
# COURSE REVIEWS
# ============================================================

class CourseReviewListCreateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, course_id):

        course = get_object_or_404(
            Course,
            id=course_id
        )

        reviews = course.reviews.select_related(
            "user"
        )

        serializer = CourseReviewSerializer(
            reviews,
            many=True
        )

        return Response(serializer.data)

    def post(self, request, course_id):

        course = get_object_or_404(
            Course,
            id=course_id,
            status="APPROVED"
        )

        enrollment = Enrollment.objects.filter(
            user=request.user,
            course=course
        ).first()

        if not enrollment:

            return Response(
                {
                    "detail": (
                        "You must be enrolled "
                        "to review this course."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        if CourseReview.objects.filter(
            course=course,
            user=request.user
        ).exists():

            return Response(
                {
                    "detail": (
                        "You have already reviewed "
                        "this course."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = CourseReviewSerializer(
            data={
                **request.data,
                "course": course.id
            }
        )

        if serializer.is_valid():

            review = serializer.save(
                user=request.user
            )

            return Response(
                CourseReviewSerializer(review).data,
                status=status.HTTP_201_CREATED
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


# ============================================================
# MY CERTIFICATES
# ============================================================

class MyCertificatesAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        certificates = Certificate.objects.filter(
            enrollment__user=request.user
        ).select_related(
            "enrollment__course"
        )

        serializer = CertificateSerializer(
            certificates,
            many=True
        )

        return Response(serializer.data)


# ============================================================
# QUIZ
# ============================================================

class LessonQuizAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, lesson_id):

        lesson = get_object_or_404(
            Lesson,
            id=lesson_id
        )

        quiz = get_object_or_404(
            Quiz,
            lesson=lesson
        )

        serializer = QuizSerializer(
            quiz
        )

        return Response(serializer.data)


# ============================================================
# QUIZ QUESTIONS
# ============================================================

class QuizQuestionsAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, quiz_id):

        quiz = get_object_or_404(
            Quiz,
            id=quiz_id
        )

        questions = quiz.questions.all()

        serializer = QuestionSerializer(
            questions,
            many=True
        )

        return Response(serializer.data)


# ============================================================
# QUIZ ATTEMPT
# ============================================================

class QuizAttemptAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, quiz_id):

        quiz = get_object_or_404(
            Quiz,
            id=quiz_id
        )

        enrollment = get_object_or_404(
            Enrollment,
            user=request.user,
            course=quiz.lesson.course
        )

        answers = request.data.get(
            "answers",
            {}
        )

        questions = quiz.questions.all()

        total_questions = questions.count()
        score = 0

        for question in questions:

            answer = answers.get(
                str(question.id)
            )

            if answer == question.correct_answer:

                score += 1

        if total_questions > 0:

            percentage = round(
                (score / total_questions) * 100
            )

        else:

            percentage = 0

        passed = (
            percentage >= quiz.passing_score
        )

        attempt = QuizAttempt.objects.create(
            enrollment=enrollment,
            quiz=quiz,
            score=score,
            total_questions=total_questions,
            percentage=percentage,
            passed=passed
        )

        serializer = QuizAttemptSerializer(
            attempt
        )

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED
        )


# ============================================================
# MY QUIZ ATTEMPTS
# ============================================================

class MyQuizAttemptsAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        attempts = QuizAttempt.objects.filter(
            enrollment__user=request.user
        ).select_related(
            "quiz",
            "enrollment"
        )

        serializer = QuizAttemptSerializer(
            attempts,
            many=True
        )

        return Response(serializer.data)
from api.pagination import OrderedCursorPagination, PagedAPIView
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction
from django.db.models import Max

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .services import LearningService
from .age_permissions import AgeSafeLearningPermission, courses_for
from .models import (
    LearningCategory,
    Course,
    CourseModule,
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
    LessonCompletionInput,
    QuizAttemptInput,
    CourseRejectionInput,
    StudioQuizInput,
    StudioQuestionInput,
    StudioQuestionSerializer,
    CourseModuleSerializer,
)


# ============================================================
# LEARNING CATEGORIES
# ============================================================

class LearningCategoryListAPIView(APIView):

    permission_classes = [IsAuthenticated, AgeSafeLearningPermission]

    def get(self, request):

        categories = LearningCategory.objects.all()

        serializer = LearningCategorySerializer(
            categories,
            many=True,
            context={"default_category_id": self.default_category_id(request.user)},
        )

        return Response(serializer.data)

    @staticmethod
    def default_category_id(user):
        from .category_defaults import creator_course_category
        category = creator_course_category(user)
        return category.pk if category else None


# ============================================================
# COURSES
# ============================================================

class CourseListAPIView(PagedAPIView):

    permission_classes = [IsAuthenticated, AgeSafeLearningPermission]

    def get(self, request):

        courses = Course.objects.filter(
            status="APPROVED"
        ).select_related(
            "creator",
            "category"
        )

        courses = courses_for(request.user, courses)
        serializer = CourseSerializer(
            self.page(request, courses),
            many=True
        )

        return Response(serializer.data)


# ============================================================
# COURSE DETAIL
# ============================================================

class CourseDetailAPIView(APIView):

    permission_classes = [IsAuthenticated, AgeSafeLearningPermission]

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

    def patch(self, request, course_id):
        course = get_object_or_404(Course, id=course_id)
        if course.creator_id != request.user.id or not LearningService.can_create_course(request.user):
            return Response({"detail": "Only the course creator can edit this course."}, status=status.HTTP_403_FORBIDDEN)
        if course.status not in {"DRAFT", "REJECTED"}:
            return Response({"detail": "Only draft or rejected courses can be edited."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = CourseCreateSerializer(course, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(CourseSerializer(course).data, status=status.HTTP_200_OK)


class CourseSubmissionReadinessAPIView(APIView):
    permission_classes = [IsAuthenticated, AgeSafeLearningPermission]

    def get(self, request, course_id):
        course = get_object_or_404(Course, id=course_id)
        if course.creator_id != request.user.pk or not LearningService.can_create_course(request.user):
            return Response({'detail': 'Only the course creator can view submission readiness.'}, status=403)
        if course.status not in {'DRAFT', 'REJECTED'}:
            return Response({'detail': 'Readiness is available while a course is editable.'}, status=400)
        checklist = LearningService.submission_checklist(course)
        return Response({'ready': all(item['ready'] for item in checklist), 'checks': checklist})


# ============================================================
# CREATE COURSE
# ============================================================

class CourseCreateAPIView(APIView):

    permission_classes = [IsAuthenticated, AgeSafeLearningPermission]

    def post(self, request):
        if not LearningService.can_create_course(request.user):
            return Response({'detail': 'You do not have permission to create courses.'}, status=403)
        serializer = CourseCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        course = serializer.save(creator=request.user)
        return Response(CourseSerializer(course).data, status=201)


# ============================================================
# MY COURSES
# ============================================================

class MyCoursesAPIView(PagedAPIView):

    permission_classes = [IsAuthenticated, AgeSafeLearningPermission]

    def get(self, request):

        courses = Course.objects.filter(
            creator=request.user
        ).select_related(
            "category"
        )

        courses = courses_for(request.user, courses)
        serializer = CourseSerializer(
            self.page(request, courses),
            many=True
        )

        return Response(serializer.data)

# ============================================================
# SUBMIT COURSE FOR REVIEW
# ============================================================

class CourseSubmitAPIView(APIView):

    permission_classes = [IsAuthenticated, AgeSafeLearningPermission]

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

    permission_classes = [IsAuthenticated, AgeSafeLearningPermission]

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

    permission_classes = [IsAuthenticated, AgeSafeLearningPermission]

    def post(self, request, course_id):
        if request.user.role != 'ADMIN':
            return Response({'detail': 'Only ADMIN users can reject courses.'}, status=403)
        course = get_object_or_404(Course, id=course_id)
        data = CourseRejectionInput(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            course = LearningService.reject_course(course, data.validated_data['rejection_reason'])
        except ValueError as error:
            return Response({'detail': str(error)}, status=400)
        return Response(CourseSerializer(course).data)
# ============================================================
# LESSONS FOR COURSE
# ============================================================

class LessonPagination(OrderedCursorPagination):
    ordering = ('order', 'pk')


class CourseLessonsAPIView(PagedAPIView):
    pagination_class = LessonPagination

    permission_classes = [IsAuthenticated, AgeSafeLearningPermission]

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
            self.page(request, lessons),
            many=True
        )

        data = serializer.data
        locked = not course.is_free and course.creator_id != request.user.pk and request.user.role != 'ADMIN' and not Enrollment.objects.filter(course=course, user=request.user).exists()
        data = [{**lesson, 'is_locked': bool(locked), **({'video': None, 'notes': None, 'captions': None, 'transcript': '', 'caption_language': ''} if locked else {})} for lesson in data]
        return Response(data)


class CourseModulesAPIView(APIView):
    permission_classes = [IsAuthenticated, AgeSafeLearningPermission]

    @staticmethod
    def _available(course, user):
        return course.status == 'APPROVED' or course.creator_id == user.pk or user.role == 'ADMIN'

    def get(self, request, course_id):
        course = get_object_or_404(Course, pk=course_id)
        if not self._available(course, request.user):
            return Response({'detail': 'This course is not available.'}, status=404)
        return Response(CourseModuleSerializer(course.modules.all(), many=True).data)

    @transaction.atomic
    def post(self, request, course_id):
        course = get_object_or_404(Course.objects.select_for_update(), pk=course_id)
        if course.creator_id != request.user.pk or not LearningService.can_create_course(request.user):
            return Response({'detail': 'Only the course creator can manage course modules.'}, status=403)
        if course.status not in {'DRAFT', 'REJECTED'}:
            return Response({'detail': 'Modules cannot be changed while the course is pending or published.'}, status=400)
        data = {key: request.data.get(key) for key in request.data}
        if 'order' not in data:
            data['order'] = (course.modules.aggregate(last=Max('order'))['last'] or 0) + 1
        serializer = CourseModuleSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        module = CourseModule.objects.create(course=course, **serializer.validated_data)
        return Response(CourseModuleSerializer(module).data, status=201)


class CourseModuleDetailAPIView(APIView):
    permission_classes = [IsAuthenticated, AgeSafeLearningPermission]

    @transaction.atomic
    def patch(self, request, module_id):
        module = get_object_or_404(CourseModule.objects.select_related('course').select_for_update(), pk=module_id)
        course = Course.objects.select_for_update().get(pk=module.course_id)
        if course.creator_id != request.user.pk or not LearningService.can_create_course(request.user):
            return Response({'detail': 'Only the course creator can manage course modules.'}, status=403)
        if course.status not in {'DRAFT', 'REJECTED'}:
            return Response({'detail': 'Modules cannot be changed while the course is pending or published.'}, status=400)
        data = {key: request.data.get(key) for key in request.data if key in {'title', 'description', 'order'}}
        serializer = CourseModuleSerializer(module, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @transaction.atomic
    def delete(self, request, module_id):
        module = get_object_or_404(CourseModule.objects.select_related('course').select_for_update(), pk=module_id)
        course = Course.objects.select_for_update().get(pk=module.course_id)
        if course.creator_id != request.user.pk or not LearningService.can_create_course(request.user):
            return Response({'detail': 'Only the course creator can manage course modules.'}, status=403)
        if course.status not in {'DRAFT', 'REJECTED'}:
            return Response({'detail': 'Modules cannot be changed while the course is pending or published.'}, status=400)
        # SET_NULL keeps every lesson, quiz, progress row, attempt and certificate intact.
        module.delete()
        return Response(status=204)


# ============================================================
# CREATE LESSON
# ============================================================

class LessonCreateAPIView(APIView):

    permission_classes = [IsAuthenticated, AgeSafeLearningPermission]

    @transaction.atomic
    def post(self, request, course_id):

        course = get_object_or_404(
            Course.objects.select_for_update(),
            id=course_id
        )

        if course.creator_id != request.user.pk or not LearningService.can_create_course(request.user):

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

        # Flatten multipart values without deep-copying temporary upload streams.
        data = {key: request.data.get(key) for key in request.data}
        if data.get('module') in {'', 'none', 'null'}:
            data['module'] = None
        data['course'] = course.id
        # The client may have only a cursor page. Serialize appends on the
        # course row and use the complete persisted lesson collection.
        data['order'] = (course.lessons.aggregate(last=Max('order'))['last'] or 0) + 1
        serializer = LessonSerializer(data=data)

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

    permission_classes = [IsAuthenticated, AgeSafeLearningPermission]

    def get(self, request, lesson_id):

        lesson = get_object_or_404(
            Lesson,
            id=lesson_id
        )

        course = lesson.course

        if not course.is_free and course.creator_id != request.user.pk and request.user.role != 'ADMIN' and not Enrollment.objects.filter(course=course, user=request.user).exists():
            return Response({'detail': 'Enrollment is required to access this lesson.'}, status=403)

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

    @transaction.atomic
    def patch(self, request, lesson_id):
        lesson = get_object_or_404(Lesson.objects.select_related('course').select_for_update(), id=lesson_id)
        course = Course.objects.select_for_update().get(pk=lesson.course_id)
        if course.creator_id != request.user.pk or not LearningService.can_create_course(request.user):
            return Response({'detail': 'Only the course creator can edit this lesson.'}, status=403)
        if course.status not in {'DRAFT', 'REJECTED'}:
            return Response({'detail': 'Lessons cannot be edited while pending or published.'}, status=400)
        data = {key: request.data.get(key) for key in request.data if key in {'title', 'description', 'video', 'notes', 'captions', 'caption_language', 'transcript', 'module', 'order', 'duration'}}
        if data.get('module') in {'', 'none', 'null'}:
            data['module'] = None
        serializer = LessonSerializer(lesson, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        if 'order' in serializer.validated_data and serializer.validated_data['order'] < 1:
            return Response({'order': ['Order must be at least 1.']}, status=400)
        serializer.save()
        return Response(serializer.data)


class StudioLessonQuizAPIView(APIView):
    permission_classes = [IsAuthenticated, AgeSafeLearningPermission]

    def _lesson(self, request, lesson_id, *, lock=False):
        query = Lesson.objects.select_related('course')
        if lock:
            query = query.select_for_update()
        lesson = get_object_or_404(query, id=lesson_id)
        if lesson.course.creator_id != request.user.pk or not LearningService.can_create_course(request.user):
            return None, Response({'detail': 'Only the course creator can manage this lesson quiz.'}, status=403)
        return lesson, None

    def get(self, request, lesson_id):
        lesson, denied = self._lesson(request, lesson_id)
        if denied:
            return denied
        quiz = Quiz.objects.filter(lesson=lesson).first()
        if not quiz:
            return Response({'quiz': None, 'question_count': 0})
        return Response({'quiz': QuizSerializer(quiz).data, 'question_count': quiz.questions.count()})

    @transaction.atomic
    def post(self, request, lesson_id):
        lesson, denied = self._lesson(request, lesson_id, lock=True)
        if denied:
            return denied
        course = Course.objects.select_for_update().get(pk=lesson.course_id)
        if course.status not in {'DRAFT', 'REJECTED'}:
            return Response({'detail': 'Quiz content cannot be changed while pending or published.'}, status=400)
        if Quiz.objects.filter(lesson=lesson).exists():
            return Response({'detail': 'This lesson already has a quiz.'}, status=409)
        data = StudioQuizInput(data=request.data)
        data.is_valid(raise_exception=True)
        quiz = Quiz.objects.create(lesson=lesson, **data.validated_data)
        return Response(QuizSerializer(quiz).data, status=201)

    @transaction.atomic
    def patch(self, request, lesson_id):
        lesson, denied = self._lesson(request, lesson_id, lock=True)
        if denied:
            return denied
        course = Course.objects.select_for_update().get(pk=lesson.course_id)
        if course.status not in {'DRAFT', 'REJECTED'}:
            return Response({'detail': 'Quiz content cannot be changed while pending or published.'}, status=400)
        quiz = get_object_or_404(Quiz.objects.select_for_update(), lesson=lesson)
        data = StudioQuizInput(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        for key, value in data.validated_data.items():
            setattr(quiz, key, value)
        quiz.save(update_fields=list(data.validated_data))
        return Response(QuizSerializer(quiz).data)


class StudioQuizQuestionsAPIView(PagedAPIView):
    permission_classes = [IsAuthenticated, AgeSafeLearningPermission]
    pagination_class = OrderedCursorPagination

    def _quiz(self, request, quiz_id, *, lock=False):
        query = Quiz.objects.select_related('lesson__course')
        if lock:
            query = query.select_for_update()
        quiz = get_object_or_404(query, id=quiz_id)
        course = quiz.lesson.course
        if course.creator_id != request.user.pk or not LearningService.can_create_course(request.user):
            return None, Response({'detail': 'Only the course creator can manage quiz questions.'}, status=403)
        return quiz, None

    def get(self, request, quiz_id):
        quiz, denied = self._quiz(request, quiz_id)
        if denied:
            return denied
        return Response(StudioQuestionSerializer(self.page(request, quiz.questions.all().order_by('id')), many=True).data)

    @transaction.atomic
    def post(self, request, quiz_id):
        quiz, denied = self._quiz(request, quiz_id, lock=True)
        if denied:
            return denied
        course = Course.objects.select_for_update().get(pk=quiz.lesson.course_id)
        if course.status not in {'DRAFT', 'REJECTED'}:
            return Response({'detail': 'Quiz content cannot be changed while pending or published.'}, status=400)
        data = StudioQuestionInput(data=request.data)
        data.is_valid(raise_exception=True)
        question = Question.objects.create(quiz=quiz, **data.validated_data)
        return Response(StudioQuestionSerializer(question).data, status=201)


class StudioQuestionDetailAPIView(APIView):
    permission_classes = [IsAuthenticated, AgeSafeLearningPermission]

    @transaction.atomic
    def patch(self, request, question_id):
        question = get_object_or_404(Question.objects.select_related('quiz__lesson__course').select_for_update(), id=question_id)
        course = Course.objects.select_for_update().get(pk=question.quiz.lesson.course_id)
        if course.creator_id != request.user.pk or not LearningService.can_create_course(request.user):
            return Response({'detail': 'Only the course creator can edit this question.'}, status=403)
        if course.status not in {'DRAFT', 'REJECTED'}:
            return Response({'detail': 'Quiz content cannot be changed while pending or published.'}, status=400)
        data = StudioQuestionInput(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        for key, value in data.validated_data.items():
            setattr(question, key, value)
        question.save(update_fields=list(data.validated_data))
        return Response(StudioQuestionSerializer(question).data)


# ============================================================
# ENROLL IN COURSE
# ============================================================

class CourseEnrollmentAPIView(APIView):

    permission_classes = [IsAuthenticated, AgeSafeLearningPermission]

    def post(self, request, course_id):
        course = get_object_or_404(Course, id=course_id, status='APPROVED')
        try:
            enrollment, created = LearningService.enroll(course, request.user)
        except ValueError as error:
            return Response({'detail': str(error)}, status=402)
        if not created:
            return Response({'detail': 'You are already enrolled.'}, status=400)
        return Response(EnrollmentSerializer(enrollment).data, status=201)


# ============================================================
# MY ENROLLMENTS
# ============================================================

class MyEnrollmentsAPIView(PagedAPIView):

    permission_classes = [IsAuthenticated, AgeSafeLearningPermission]

    def get(self, request):

        enrollments = Enrollment.objects.filter(
            user=request.user
        ).select_related(
            "course"
        )

        enrollments = enrollments.filter(course__in=courses_for(request.user, Course.objects.all()))
        serializer = EnrollmentSerializer(
            self.page(request, enrollments),
            many=True
        )

        return Response(serializer.data)


# ============================================================
# LESSON PROGRESS
# ============================================================

class LessonProgressAPIView(APIView):

    permission_classes = [IsAuthenticated, AgeSafeLearningPermission]

    def post(self, request, lesson_id):
        lesson = get_object_or_404(Lesson.objects.select_related('course'), id=lesson_id)
        LearningService.require_quiz_access(request.user, lesson.course)
        data = LessonCompletionInput(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            progress, certificate = LearningService.set_lesson_completion(lesson, request.user, data.validated_data['completed'])
        except ValueError as error:
            return Response({'detail': str(error)}, status=400)
        try:
            LearningService.ensure_certificate_pdf(certificate)
        except Exception:
            # The durable progress and certificate identity remain retryable.
            return Response({'detail': 'Progress saved; certificate PDF is temporarily unavailable. Retry completion to generate it.'}, status=503)
        return Response(LessonProgressSerializer(progress).data)


# ============================================================
# COURSE PROGRESS
# ============================================================

class CourseProgressAPIView(APIView):

    permission_classes = [IsAuthenticated, AgeSafeLearningPermission]

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
                "completed_lesson_ids": list(LessonProgress.objects.filter(
                    enrollment=enrollment, completed=True,
                ).values_list("lesson_id", flat=True)),
            }
        )


# ============================================================
# COURSE REVIEWS
# ============================================================

class CourseReviewListCreateAPIView(PagedAPIView):

    permission_classes = [IsAuthenticated, AgeSafeLearningPermission]

    def get(self, request, course_id):

        course = get_object_or_404(
            Course,
            id=course_id
        )

        reviews = course.reviews.select_related(
            "user"
        )

        serializer = CourseReviewSerializer(
            self.page(request, reviews),
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

class MyCertificatesAPIView(PagedAPIView):

    permission_classes = [IsAuthenticated, AgeSafeLearningPermission]

    def get(self, request):

        certificates = Certificate.objects.filter(
            enrollment__user=request.user
        ).select_related(
            "enrollment__course"
        )

        serializer = CertificateSerializer(
            self.page(request, certificates),
            many=True
        )

        return Response(serializer.data)


# ============================================================
# QUIZ
# ============================================================

class LessonQuizAPIView(APIView):

    permission_classes = [IsAuthenticated, AgeSafeLearningPermission]

    def get(self, request, lesson_id):
        lesson = get_object_or_404(Lesson.objects.select_related('course'), id=lesson_id)
        LearningService.require_quiz_access(request.user, lesson.course)
        quiz = get_object_or_404(Quiz, lesson=lesson)
        return Response(QuizSerializer(quiz).data)


# ============================================================
# QUIZ QUESTIONS
# ============================================================

class QuizQuestionsAPIView(PagedAPIView):
    pagination_class = OrderedCursorPagination

    permission_classes = [IsAuthenticated, AgeSafeLearningPermission]

    def get(self, request, quiz_id):
        quiz = get_object_or_404(Quiz.objects.select_related('lesson__course'), id=quiz_id)
        LearningService.require_quiz_access(request.user, quiz.lesson.course)
        return Response(QuestionSerializer(self.page(request, quiz.questions.all()), many=True).data)


# ============================================================
# QUIZ ATTEMPT
# ============================================================

class QuizAttemptAPIView(APIView):

    permission_classes = [IsAuthenticated, AgeSafeLearningPermission]

    def post(self, request, quiz_id):
        quiz = get_object_or_404(Quiz.objects.select_related('lesson__course'), id=quiz_id)
        LearningService.require_quiz_access(request.user, quiz.lesson.course)
        data = QuizAttemptInput(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            attempt = LearningService.record_quiz_attempt(quiz, request.user, data.validated_data['answers'])
        except ValueError as error:
            return Response({'detail': str(error)}, status=400)
        result = dict(QuizAttemptSerializer(attempt).data)
        result['question_feedback'] = attempt.question_feedback
        return Response(result, status=201)


# ============================================================
# MY QUIZ ATTEMPTS
# ============================================================

class MyQuizAttemptsAPIView(PagedAPIView):

    permission_classes = [IsAuthenticated, AgeSafeLearningPermission]

    def get(self, request):

        attempts = QuizAttempt.objects.filter(
            enrollment__user=request.user
        ).select_related(
            "quiz",
            "enrollment"
        ).order_by('-attempted_at', '-pk')

        serializer = QuizAttemptSerializer(
            self.page(request, attempts),
            many=True
        )

        return Response(serializer.data)


class PendingCoursesAPIView(PagedAPIView):

    permission_classes = [IsAuthenticated, AgeSafeLearningPermission]

    def get(self, request):
        if request.user.role != "ADMIN":
            return Response({"detail": "Only administrators can review courses."}, status=status.HTTP_403_FORBIDDEN)
        courses = Course.objects.filter(status="PENDING").select_related("category", "creator")
        return Response(CourseSerializer(self.page(request, courses), many=True).data)

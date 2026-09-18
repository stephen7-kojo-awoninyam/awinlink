from django.urls import path

from .api_views import (
    CourseSubmitAPIView,
    LearningCategoryListAPIView,
    CourseListAPIView,
    CourseDetailAPIView,
    CourseCreateAPIView,
    MyCoursesAPIView,
    CourseLessonsAPIView,
    LessonCreateAPIView,
    LessonDetailAPIView,
    CourseEnrollmentAPIView,
    MyEnrollmentsAPIView,
    LessonProgressAPIView,
    CourseProgressAPIView,
    CourseReviewListCreateAPIView,
    MyCertificatesAPIView,
    LessonQuizAPIView,
    QuizQuestionsAPIView,
    QuizAttemptAPIView,
    MyQuizAttemptsAPIView,
    CourseApproveAPIView,
    CourseRejectAPIView,
)


urlpatterns = [

    # =====================================================
    # LEARNING CATEGORIES
    # =====================================================

    path(
        "categories/",
        LearningCategoryListAPIView.as_view(),
        name="learning_categories"
    ),


    # =====================================================
    # COURSES
    # =====================================================

    path(
        "courses/",
        CourseListAPIView.as_view(),
        name="course_list"
    ),

    path(
        "courses/create/",
        CourseCreateAPIView.as_view(),
        name="course_create"
    ),

    path(
        "courses/me/",
        MyCoursesAPIView.as_view(),
        name="my_courses"
    ),
    
    path(
    "courses/<int:course_id>/submit/",
    CourseSubmitAPIView.as_view(),
    name="course_submit"
    ),

    path(
        "courses/<int:course_id>/approve/",
        CourseApproveAPIView.as_view(),
        name="course_approve"
    ),

    path(
        "courses/<int:course_id>/reject/",
        CourseRejectAPIView.as_view(),
        name="course_reject"
    ),

    path(
        "courses/<int:course_id>/",
        CourseDetailAPIView.as_view(),
        name="course_detail"
    ),

    path(
        "courses/<int:course_id>/lessons/",
        CourseLessonsAPIView.as_view(),
        name="course_lessons"
    ),

    path(
        "courses/<int:course_id>/lessons/create/",
        LessonCreateAPIView.as_view(),
        name="lesson_create"
    ),

    path(
        "courses/<int:course_id>/enroll/",
        CourseEnrollmentAPIView.as_view(),
        name="course_enroll"
    ),

    path(
        "courses/<int:course_id>/progress/",
        CourseProgressAPIView.as_view(),
        name="course_progress"
    ),

    path(
        "courses/<int:course_id>/reviews/",
        CourseReviewListCreateAPIView.as_view(),
        name="course_reviews"
    ),


    # =====================================================
    # MY LEARNING
    # =====================================================

    path(
        "my-enrollments/",
        MyEnrollmentsAPIView.as_view(),
        name="my_enrollments"
    ),

    path(
        "my-certificates/",
        MyCertificatesAPIView.as_view(),
        name="my_certificates"
    ),


    # =====================================================
    # LESSONS
    # =====================================================

    path(
        "lessons/<int:lesson_id>/",
        LessonDetailAPIView.as_view(),
        name="lesson_detail"
    ),

    path(
        "lessons/<int:lesson_id>/progress/",
        LessonProgressAPIView.as_view(),
        name="lesson_progress"
    ),

    path(
        "lessons/<int:lesson_id>/quiz/",
        LessonQuizAPIView.as_view(),
        name="lesson_quiz"
    ),


    # =====================================================
    # QUIZZES
    # =====================================================

    path(
        "quizzes/<int:quiz_id>/questions/",
        QuizQuestionsAPIView.as_view(),
        name="quiz_questions"
    ),

    path(
        "quizzes/<int:quiz_id>/attempt/",
        QuizAttemptAPIView.as_view(),
        name="quiz_attempt"
    ),

    path(
        "quiz-attempts/me/",
        MyQuizAttemptsAPIView.as_view(),
        name="my_quiz_attempts"
    ),

]
from django.urls import path

from . import views


urlpatterns = [

    # =====================================================
    # COURSE DISCOVERY
    # =====================================================

    path(
        "",
        views.course_list,
        name="courses"
    ),

    path(
        "course/<slug:slug>/",
        views.course_detail,
        name="course_detail"
    ),

    # =====================================================
    # COURSE CREATION
    # =====================================================

    path(
        "create/",
        views.create_course,
        name="create_course"
    ),

    path(
        "my-courses/",
        views.my_courses,
        name="my_courses"
    ),

    path(
        "course/<int:course_id>/edit/",
        views.edit_course,
        name="edit_course"
    ),

    path(
        "course/<int:course_id>/submit/",
        views.submit_course,
        name="submit_course"
    ),
    
    # =====================================================
    # ADMIN COURSE REVIEW
    # =====================================================

    path(
        "admin/courses/",
        views.admin_courses,
        name="admin_courses"
    ),

    path(
        "admin/course/<int:course_id>/",
        views.admin_course_detail,
        name="admin_course_detail"
    ),

    path(
        "admin/course/<int:course_id>/approve/",
        views.approve_course,
        name="approve_course"
    ),

    path(
        "admin/course/<int:course_id>/reject/",
        views.reject_course,
        name="reject_course"
    ),

    # =====================================================
    # COURSE MANAGEMENT
    # =====================================================

    path(
        "course/<int:course_id>/manage/",
        views.manage_course,
        name="manage_course"
    ),

    path(
        "course/<int:course_id>/lesson/add/",
        views.add_lesson,
        name="add_lesson"
    ),

    path(
        "lesson/<int:lesson_id>/edit/",
        views.edit_lesson,
        name="edit_lesson"
    ),

    path(
        "lesson/<int:lesson_id>/delete/",
        views.delete_lesson,
        name="delete_lesson"
    ),

    # =====================================================
    # ENROLLMENT
    # =====================================================

    path(
        "course/<int:course_id>/enroll/",
        views.enroll_course,
        name="enroll_course"
    ),

    path(
        "my-learning/",
        views.my_learning,
        name="my_learning"
    ),

    # =====================================================
    # LESSONS
    # =====================================================

    path(
        "lesson/<int:lesson_id>/",
        views.lesson_detail,
        name="lesson_detail"
    ),

    path(
        "lesson/<int:lesson_id>/complete/",
        views.complete_lesson,
        name="complete_lesson"
    ),

    # =====================================================
    # PROGRESS
    # =====================================================

    path(
        "course/<int:course_id>/progress/",
        views.course_progress,
        name="course_progress"
    ),

    # =====================================================
    # REVIEWS
    # =====================================================

    path(
        "course/<int:course_id>/review/",
        views.review_course,
        name="review_course"
    ),

    # =====================================================
    # QUIZZES
    # =====================================================

    path(
        "quiz/<int:quiz_id>/",
        views.take_quiz,
        name="take_quiz"
    ),
    path(
        "lesson/<int:lesson_id>/quiz/create/",
        views.create_quiz,
        name="create_quiz"
    ),
    
    path(
        "quiz/<int:quiz_id>/manage/",
        views.manage_quiz,
        name="manage_quiz"
   ),
    
    path(
    "quiz/<int:quiz_id>/question/add/",
    views.add_question,
    name="add_question"
    ),
    
    path(
    "quiz/<int:quiz_id>/edit/",
    views.edit_quiz,
    name="edit_quiz"
    ),

    path(
        "quiz/<int:quiz_id>/delete/",
        views.delete_quiz,
        name="delete_quiz"
    ),

    
    # =====================================================
    # QUESTION MANAGEMENT
    # =====================================================
    
    path(
        "quiz/<int:quiz_id>/question/add/",
        views.add_question,
        name="add_question"
    ),

    path(
        "question/<int:question_id>/edit/",
        views.edit_question,
        name="edit_question"
    ),

    path(
        "question/<int:question_id>/delete/",
        views.delete_question,
        name="delete_question"
    ),
    
    path(
    "certificate/<str:certificate_id>/",
    views.certificate_detail,
    name="certificate_detail"
    ),
    
    path(
    "certificate/<str:certificate_id>/download/",
    views.download_certificate,
    name="download_certificate"
    ),
    path(
    "my-certificates/",
    views.my_certificates,
    name="my_certificates"
    ),

    path(
        "certificate/<str:certificate_id>/",
        views.certificate_detail,
        name="certificate_detail"
    ),

    path(
        "certificate/<str:certificate_id>/download/",
        views.download_certificate,
        name="download_certificate"
    ),

    path(
        "certificate/<str:certificate_id>/",
        views.view_certificate,
        name="view_certificate"
    ),
    
    path(
    "certificates/verify/<str:certificate_id>/",
    views.verify_certificate,
    name="verify_certificate"
    ),
    
    path(
    "my-quiz-attempts/",
    views.my_quiz_attempts,
    name="my_quiz_attempts"
    ),
]
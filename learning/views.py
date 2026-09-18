from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Avg
from django.utils import timezone
from django.views.decorators.http import require_POST
import uuid
from io import BytesIO
from django.core.files.base import ContentFile
from django.http import FileResponse
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

from .utils import generate_certificate

from .models import (
    LearningCategory,
    Course,
    Lesson,
    Enrollment,
    LessonProgress,
    CourseReview,
    Quiz,
    Question,
    QuizAttempt,
    Certificate
)

from .forms import (
    LearningCategoryForm,
    CourseForm,
    LessonForm,
    CourseReviewForm,
    QuizForm,
    QuestionForm,
  
    
)


# =========================================================
# LEARNING ROLE PERMISSIONS
# =========================================================

def is_course_creator(user):
    """
    All authenticated Awinlink roles can create and
    manage their own learning content.

    Awinlink does not have an INSTRUCTOR account role.

    Course creators:
        ATHLETE
        ORGANIZATION
        SCOUT
        COACH
        ADMIN

    Course approval remains an ADMIN responsibility.
    """

    return (
        user.is_authenticated
        and user.role in [
            "ATHLETE",
            "ORGANIZATION",
            "SCOUT",
            "COACH",
            "ADMIN",
        ]
    )


def is_admin(user):
    """
    Users who are allowed to perform Learning administration.
    """
    return (
        user.is_authenticated
        and user.role == "ADMIN"
    )


# =========================================================
# COURSE LIST
# =========================================================

@login_required
def course_list(request):

    courses = Course.objects.filter(
        status="APPROVED"
    ).select_related(
        "category",
        "creator"
    )

    categories = LearningCategory.objects.all()

    category_id = request.GET.get("category")
    level = request.GET.get("level")
    search = request.GET.get("q")

    if category_id:
        courses = courses.filter(
            category_id=category_id
        )

    if level:
        courses = courses.filter(
            level=level
        )

    if search:
        courses = courses.filter(
            title__icontains=search
        )

    return render(
        request,
        "learning/course_list.html",
        {
            "courses": courses,
            "categories": categories,
        }
    )


# =========================================================
# COURSE DETAIL
# =========================================================

@login_required
def course_detail(request, slug):

    course = get_object_or_404(
        Course.objects.select_related(
            "category",
            "creator"
        ),
        slug=slug,
        status="APPROVED"
    )

    lessons = course.lessons.all()

    enrollment = Enrollment.objects.filter(
        user=request.user,
        course=course
    ).first()

    reviews = course.reviews.select_related(
        "user"
    ).all()

    average_rating = reviews.aggregate(
        average=Avg("rating")
    )["average"]

    total_reviews = reviews.count()

    return render(
        request,
        "learning/course_detail.html",
        {
            "course": course,
            "lessons": lessons,
            "enrollment": enrollment,
            "reviews": reviews,
            "average_rating": average_rating,
            "total_reviews": total_reviews,
        }
    )


# =========================================================
# CREATE COURSE
# =========================================================

@login_required
@user_passes_test(is_course_creator)
def create_course(request):

    if request.method == "POST":

        form = CourseForm(
            request.POST,
            request.FILES
        )

        if form.is_valid():

            course = form.save(
                commit=False
            )

            course.creator = request.user
            course.status = "DRAFT"

            course.save()

            messages.success(
                request,
                "Course created successfully."
            )

            return redirect(
                "manage_course",
                course_id=course.id
            )

    else:

        form = CourseForm()

    return render(
        request,
        "learning/create_course.html",
        {
            "form": form
        }
    )


# =========================================================
# ENROLL IN COURSE
# =========================================================

@login_required
def enroll_course(request, course_id):

    course = get_object_or_404(
        Course,
        id=course_id,
        status="APPROVED"
    )

    enrollment, created = Enrollment.objects.get_or_create(
        user=request.user,
        course=course
    )

    if created:

        messages.success(
            request,
            f"You have enrolled in {course.title}."
        )

    else:

        messages.info(
            request,
            "You are already enrolled in this course."
        )

    return redirect(
        "course_detail",
        slug=course.slug
    )


# =========================================================
# MY LEARNING / LEARNING DASHBOARD
# =========================================================

@login_required
def my_learning(request):

    enrollments = Enrollment.objects.filter(
        user=request.user
    ).select_related(
        "course",
        "course__category"
    ).prefetch_related(
        "lesson_progress"
    )

    total_courses = enrollments.count()

    completed_courses = enrollments.filter(
        completed=True
    ).count()

    in_progress_courses = enrollments.filter(
        completed=False
    ).count()

    certificates = Certificate.objects.filter(
        enrollment__user=request.user
    ).count()

    quiz_attempts = QuizAttempt.objects.filter(
        enrollment__user=request.user
    ).count()

    # -----------------------------------------------------
    # CALCULATE PROGRESS FOR EACH COURSE
    # -----------------------------------------------------

    for enrollment in enrollments:

        total_lessons = enrollment.course.lessons.count()

        completed_lessons = enrollment.lesson_progress.filter(
            completed=True
        ).count()

        if total_lessons > 0:

            enrollment.progress_percentage = round(
                (
                    completed_lessons /
                    total_lessons
                ) * 100
            )

        else:

            enrollment.progress_percentage = 0

    return render(
        request,
        "learning/my_learning.html",
        {
            "enrollments": enrollments,
            "total_courses": total_courses,
            "completed_courses": completed_courses,
            "in_progress_courses": in_progress_courses,
            "certificates": certificates,
            "quiz_attempts": quiz_attempts,
        }
    )


# =========================================================
# LESSON
# =========================================================

@login_required
def lesson_detail(request, lesson_id):

    lesson = get_object_or_404(
        Lesson.objects.select_related(
            "course",
            "quiz"
        ),
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

    lessons = lesson.course.lessons.all()

    return render(
        request,
        "learning/lesson_detail.html",
        {
            "lesson": lesson,
            "course": lesson.course,
            "enrollment": enrollment,
            "progress": progress,
            "lessons": lessons,
            "quiz": getattr(lesson, "quiz", None),
        }
    )



# =========================================================
# COMPLETE LESSON
# =========================================================

@login_required
def complete_lesson(request, lesson_id):

    lesson = get_object_or_404(
        Lesson.objects.select_related(
            "course"
        ),
        id=lesson_id
    )

    course = lesson.course

    enrollment = get_object_or_404(
        Enrollment,
        user=request.user,
        course=course
    )

    # -----------------------------------------------------
    # ONLY POST
    # -----------------------------------------------------

    if request.method != "POST":

        return redirect(
            "lesson_detail",
            lesson_id=lesson.id
        )

    # -----------------------------------------------------
    # GET CURRENT PROGRESS
    # -----------------------------------------------------

    progress, created = LessonProgress.objects.get_or_create(
        enrollment=enrollment,
        lesson=lesson
    )

    # -----------------------------------------------------
    # LESSON WITH QUIZ
    # -----------------------------------------------------

    # If the lesson has a quiz, the learner must have
    # passed the quiz before the lesson can be completed.

    if hasattr(lesson, "quiz"):

        quiz = lesson.quiz

        passed_quiz = QuizAttempt.objects.filter(
            enrollment=enrollment,
            quiz=quiz,
            passed=True
        ).exists()

        if not passed_quiz:

            messages.warning(
                request,
                "You must pass the quiz for this lesson before completing it."
            )

            return redirect(
                "take_quiz",
                quiz_id=quiz.id
            )

    # -----------------------------------------------------
    # MARK LESSON COMPLETE
    # -----------------------------------------------------

    if not progress.completed:

        progress.completed = True
        progress.completed_at = timezone.now()

        progress.save(
            update_fields=[
                "completed",
                "completed_at"
            ]
        )

    # -----------------------------------------------------
    # COURSE PROGRESS
    # -----------------------------------------------------

    total_lessons = course.lessons.count()

    completed_lessons = LessonProgress.objects.filter(
        enrollment=enrollment,
        lesson__course=course,
        completed=True
    ).count()

    # -----------------------------------------------------
    # CHECK REQUIRED QUIZZES
    # -----------------------------------------------------

    quizzes = Quiz.objects.filter(
        lesson__course=course
    )

    total_quizzes = quizzes.count()

    passed_quizzes = QuizAttempt.objects.filter(
        enrollment=enrollment,
        quiz__in=quizzes,
        passed=True
    ).values(
        "quiz_id"
    ).distinct().count()

    # -----------------------------------------------------
    # DETERMINE LESSON COMPLETION
    # -----------------------------------------------------

    lessons_completed = (
        total_lessons > 0
        and completed_lessons >= total_lessons
    )

    # -----------------------------------------------------
    # DETERMINE QUIZ COMPLETION
    # -----------------------------------------------------

    quizzes_completed = (
        passed_quizzes >= total_quizzes
    )

    # -----------------------------------------------------
    # DETERMINE COURSE COMPLETION
    # -----------------------------------------------------

    course_completed = (
        lessons_completed
        and quizzes_completed
    )

    # -----------------------------------------------------
    # COURSE COMPLETED
    # -----------------------------------------------------

    if course_completed:

        # -------------------------------------------------
        # MARK ENROLLMENT COMPLETED
        # -------------------------------------------------

        if not enrollment.completed:

            enrollment.completed = True

            enrollment.save(
                update_fields=[
                    "completed"
                ]
            )

        # -------------------------------------------------
        # GENERATE CERTIFICATE
        # -------------------------------------------------

        certificate = generate_certificate(
            enrollment
        )

        if certificate:

            messages.success(
                request,
                "Congratulations! You have completed the course and earned your certificate."
            )

        else:

            messages.warning(
                request,
                "Course completed, but the certificate could not be generated."
            )

    else:

        # -------------------------------------------------
        # COURSE STILL IN PROGRESS
        # -------------------------------------------------

        if total_quizzes > passed_quizzes:

            remaining_quizzes = (
                total_quizzes - passed_quizzes
            )

            messages.success(
                request,
                f"Lesson marked as complete. "
                f"You still need to pass {remaining_quizzes} "
                f"quiz(es) to complete the course."
            )

        else:

            messages.success(
                request,
                "Lesson marked as complete."
            )

    return redirect(
        "lesson_detail",
        lesson_id=lesson.id
    )
    
    
# =========================================================
# MY COURSES
# =========================================================

@login_required
@user_passes_test(is_course_creator)
def my_courses(request):

    courses = Course.objects.filter(
        creator=request.user
    ).select_related(
        "category"
    )

    return render(
        request,
        "learning/my_courses.html",
        {
            "courses": courses
        }
    )


# =========================================================
# EDIT COURSE
# =========================================================

@login_required
@user_passes_test(is_course_creator)
def edit_course(request, course_id):

    course = get_object_or_404(
        Course,
        id=course_id,
        creator=request.user
    )

    # -----------------------------------------------------
    # PENDING AND APPROVED COURSES CANNOT BE EDITED
    # -----------------------------------------------------

    if course.status in ["PENDING", "APPROVED"]:

        messages.warning(
            request,
            "Courses pending approval or already approved cannot be edited."
        )

        return redirect(
            "my_courses"
        )

    # -----------------------------------------------------
    # EDIT COURSE
    # -----------------------------------------------------

    if request.method == "POST":

        form = CourseForm(
            request.POST,
            request.FILES,
            instance=course
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Course updated successfully."
            )

            return redirect(
                "my_courses"
            )

    else:

        form = CourseForm(
            instance=course
        )

    return render(
        request,
        "learning/edit_course.html",
        {
            "form": form,
            "course": course
        }
    )


# =========================================================
# SUBMIT COURSE FOR APPROVAL
# =========================================================

@login_required
@user_passes_test(is_course_creator)
def submit_course(request, course_id):

    course = get_object_or_404(
        Course,
        id=course_id,
        creator=request.user
    )

    # -----------------------------------------------------
    # ONLY DRAFT OR REJECTED COURSES CAN BE SUBMITTED
    # -----------------------------------------------------

    if course.status not in ["DRAFT", "REJECTED"]:

        messages.warning(
            request,
            "Only draft or rejected courses can be submitted."
        )

        return redirect(
            "my_courses"
        )

    # -----------------------------------------------------
    # COURSE MUST HAVE AT LEAST ONE LESSON
    # -----------------------------------------------------

    if not course.lessons.exists():

        messages.warning(
            request,
            "Add at least one lesson before submitting the course."
        )

        return redirect(
            "my_courses"
        )

    # -----------------------------------------------------
    # SUBMIT COURSE
    # -----------------------------------------------------

    course.status = "PENDING"

    # Clear the previous rejection reason when
    # a rejected course is resubmitted.
    course.rejection_reason = ""

    course.save(
        update_fields=[
            "status",
            "rejection_reason"
        ]
    )

    messages.success(
        request,
        "Course submitted for approval."
    )

    return redirect(
        "my_courses"
    )


# =========================================================
# ADD LESSON
# =========================================================

@login_required
@user_passes_test(is_course_creator)
def add_lesson(request, course_id):

    course = get_object_or_404(
        Course,
        id=course_id,
        creator=request.user
    )

    # -----------------------------------------------------
    # PENDING AND APPROVED COURSES CANNOT BE MODIFIED
    # -----------------------------------------------------

    if course.status in ["PENDING", "APPROVED"]:

        messages.warning(
            request,
            "Lessons cannot be modified while the course is pending approval or approved."
        )

        return redirect(
            "my_courses"
        )

    # -----------------------------------------------------
    # ADD LESSON
    # -----------------------------------------------------

    if request.method == "POST":

        form = LessonForm(
            request.POST,
            request.FILES
        )

        if form.is_valid():

            lesson = form.save(
                commit=False
            )

            lesson.course = course

            lesson.save()

            messages.success(
                request,
                "Lesson added successfully."
            )

            return redirect(
                "manage_course",
                course_id=course.id
            )

    else:

        next_order = course.lessons.count() + 1

        form = LessonForm(
            initial={
                "order": next_order
            }
        )

    return render(
        request,
        "learning/add_lesson.html",
        {
            "form": form,
            "course": course
        }
    )

# =========================================================
# MANAGE COURSE
# =========================================================

@login_required
@user_passes_test(is_course_creator)
def manage_course(request, course_id):

    course = get_object_or_404(
        Course,
        id=course_id,
        creator=request.user
    )

    lessons = course.lessons.all()

    return render(
        request,
        "learning/manage_course.html",
        {
            "course": course,
            "lessons": lessons
        }
    )


# =========================================================
# EDIT LESSON
# =========================================================

@login_required
@user_passes_test(is_course_creator)
def edit_lesson(request, lesson_id):

    lesson = get_object_or_404(
        Lesson.objects.select_related(
            "course"
        ),
        id=lesson_id
    )

    course = lesson.course

    # -----------------------------------------------------
    # VERIFY COURSE OWNERSHIP
    # -----------------------------------------------------

    if course.creator != request.user:

        messages.error(
            request,
            "You are not authorized to edit this lesson."
        )

        return redirect(
            "course_detail",
            slug=course.slug
        )

    # -----------------------------------------------------
    # PENDING AND APPROVED COURSES CANNOT BE MODIFIED
    # -----------------------------------------------------

    if course.status in ["PENDING", "APPROVED"]:

        messages.warning(
            request,
            "Lessons cannot be modified while the course is pending approval or approved."
        )

        return redirect(
            "manage_course",
            course_id=course.id
        )

    # -----------------------------------------------------
    # EDIT LESSON
    # -----------------------------------------------------

    if request.method == "POST":

        form = LessonForm(
            request.POST,
            request.FILES,
            instance=lesson
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Lesson updated successfully."
            )

            return redirect(
                "manage_course",
                course_id=course.id
            )

    else:

        form = LessonForm(
            instance=lesson
        )

    return render(
        request,
        "learning/edit_lesson.html",
        {
            "form": form,
            "lesson": lesson,
            "course": course
        }
    )


# =========================================================
# DELETE LESSON
# =========================================================

@login_required
@user_passes_test(is_course_creator)
def delete_lesson(request, lesson_id):

    lesson = get_object_or_404(
        Lesson.objects.select_related(
            "course"
        ),
        id=lesson_id
    )

    course = lesson.course

    # -----------------------------------------------------
    # VERIFY COURSE OWNERSHIP
    # -----------------------------------------------------

    if course.creator != request.user:

        messages.error(
            request,
            "You are not authorized to delete this lesson."
        )

        return redirect(
            "course_detail",
            slug=course.slug
        )

    # -----------------------------------------------------
    # PENDING AND APPROVED COURSES CANNOT BE MODIFIED
    # -----------------------------------------------------

    if course.status in ["PENDING", "APPROVED"]:

        messages.warning(
            request,
            "Lessons cannot be modified while the course is pending approval or approved."
        )

        return redirect(
            "manage_course",
            course_id=course.id
        )

    # -----------------------------------------------------
    # DELETE LESSON
    # -----------------------------------------------------

    if request.method == "POST":

        lesson.delete()

        messages.success(
            request,
            "Lesson deleted successfully."
        )

    return redirect(
        "manage_course",
        course_id=course.id
    )


# =========================================================
# COURSE REVIEW
# =========================================================

@login_required
def review_course(request, course_id):

    course = get_object_or_404(
        Course,
        id=course_id,
        status="APPROVED"
    )

    enrollment = get_object_or_404(
        Enrollment,
        user=request.user,
        course=course
    )

    existing_review = CourseReview.objects.filter(
        course=course,
        user=request.user
    ).first()

    if request.method == "POST":

        form = CourseReviewForm(
            request.POST,
            instance=existing_review
        )

        if form.is_valid():

            review = form.save(
                commit=False
            )

            review.course = course
            review.user = request.user

            review.save()

            messages.success(
                request,
                "Your review has been submitted."
            )

            return redirect(
                "course_detail",
                slug=course.slug
            )

    else:

        form = CourseReviewForm(
            instance=existing_review
        )

    return render(
        request,
        "learning/review_course.html",
        {
            "course": course,
            "form": form
        }
    )

# =========================================================
# TAKE QUIZ
# =========================================================

@login_required
def take_quiz(request, quiz_id):

    quiz = get_object_or_404(
        Quiz.objects.select_related(
            "lesson",
            "lesson__course"
        ),
        id=quiz_id
    )

    lesson = quiz.lesson
    course = lesson.course

    # -----------------------------------------------------
    # VERIFY ENROLLMENT
    # -----------------------------------------------------

    enrollment = get_object_or_404(
        Enrollment,
        user=request.user,
        course=course
    )

    # -----------------------------------------------------
    # GET QUESTIONS
    # -----------------------------------------------------

    questions = quiz.questions.all().order_by("id")

    # -----------------------------------------------------
    # QUIZ MUST HAVE QUESTIONS
    # -----------------------------------------------------

    if not questions.exists():

        messages.warning(
            request,
            "This quiz does not have any questions yet."
        )

        return redirect(
            "lesson_detail",
            lesson_id=lesson.id
        )

    # -----------------------------------------------------
    # SUBMIT QUIZ
    # -----------------------------------------------------

    if request.method == "POST":

        score = 0

        total_questions = questions.count()

        # -------------------------------------------------
        # CHECK ANSWERS
        # -------------------------------------------------

        for question in questions:

            answer = request.POST.get(
                f"question_{question.id}"
            )

            if answer == question.correct_answer:

                score += 1

        # -------------------------------------------------
        # CALCULATE PERCENTAGE
        # -------------------------------------------------

        percentage = round(
            (score / total_questions) * 100
        )

        # -------------------------------------------------
        # DETERMINE PASS / FAIL
        # -------------------------------------------------

        passed = (
            percentage >= quiz.passing_score
        )

        # -------------------------------------------------
        # SAVE QUIZ ATTEMPT
        # -------------------------------------------------

        attempt = QuizAttempt.objects.create(
            enrollment=enrollment,
            quiz=quiz,
            score=score,
            total_questions=total_questions,
            percentage=percentage,
            passed=passed
        )

        # -------------------------------------------------
        # IF QUIZ PASSED
        # -------------------------------------------------

        if passed:

            messages.success(
                request,
                f"Congratulations! You passed the quiz with "
                f"{percentage}%."
            )

        else:

            messages.warning(
                request,
                f"You scored {percentage}%. "
                f"You need {quiz.passing_score}% to pass. "
                f"You can try again."
            )

        # -------------------------------------------------
        # RENDER QUIZ RESULT
        # -------------------------------------------------

        return render(
            request,
            "learning/quiz_result.html",
            {
                "quiz": quiz,
                "lesson": lesson,
                "course": course,
                "enrollment": enrollment,
                "attempt": attempt,
                "score": score,
                "total_questions": total_questions,
                "percentage": percentage,
                "passed": passed,
            }
        )

    # -----------------------------------------------------
    # DISPLAY QUIZ
    # -----------------------------------------------------

    return render(
        request,
        "learning/take_quiz.html",
        {
            "quiz": quiz,
            "lesson": lesson,
            "course": course,
            "questions": questions,
            "enrollment": enrollment,
        }
    )

   

# =========================================================
# CREATE QUIZ
# =========================================================

@login_required
@user_passes_test(is_course_creator)
def create_quiz(request, lesson_id):

    lesson = get_object_or_404(
        Lesson.objects.select_related(
            "course"
        ),
        id=lesson_id
    )

    course = lesson.course

    # -----------------------------------------------------
    # VERIFY COURSE OWNERSHIP
    # -----------------------------------------------------

    if course.creator != request.user:

        messages.error(
            request,
            "You are not authorized to manage this lesson."
        )

        return redirect(
            "course_detail",
            slug=course.slug
        )

    # -----------------------------------------------------
    # PREVENT MODIFICATION OF PENDING/APPROVED COURSES
    # -----------------------------------------------------

    if course.status in ["PENDING", "APPROVED"]:

        messages.warning(
            request,
            "You cannot create a quiz while the course is pending approval or approved."
        )

        return redirect(
            "manage_course",
            course_id=course.id
        )

    # -----------------------------------------------------
    # PREVENT DUPLICATE QUIZ
    # -----------------------------------------------------

    if hasattr(lesson, "quiz"):

        messages.info(
            request,
            "This lesson already has a quiz."
        )

        return redirect(
            "manage_course",
            course_id=course.id
        )

    # -----------------------------------------------------
    # CREATE QUIZ
    # -----------------------------------------------------

    if request.method == "POST":

        title = request.POST.get("title")
        passing_score = request.POST.get("passing_score", 70)

        if not title:

            messages.error(
                request,
                "Quiz title is required."
            )

        else:

            try:

                passing_score = int(passing_score)

            except (TypeError, ValueError):

                passing_score = 70

            if passing_score < 1 or passing_score > 100:

                messages.error(
                    request,
                    "Passing score must be between 1 and 100."
                )

            else:

                quiz = Quiz.objects.create(
                    lesson=lesson,
                    title=title,
                    passing_score=passing_score
                )

                messages.success(
                    request,
                    "Quiz created successfully."
                )

                return redirect(
                    "manage_quiz",
                    quiz_id=quiz.id
                )

    return render(
        request,
        "learning/create_quiz.html",
        {
            "lesson": lesson,
            "course": course
        }
    )


# =========================================================
# COURSE PROGRESS
# =========================================================

@login_required
def course_progress(request, course_id):

    course = get_object_or_404(
        Course,
        id=course_id
    )

    enrollment = get_object_or_404(
        Enrollment,
        user=request.user,
        course=course
    )

    # -----------------------------------------------------
    # GET COURSE LESSONS
    # -----------------------------------------------------

    lessons = list(
        course.lessons.all()
    )

    # -----------------------------------------------------
    # GET LESSON PROGRESS FOR THIS ENROLLMENT
    # -----------------------------------------------------

    progress_records = LessonProgress.objects.filter(
        enrollment=enrollment,
        lesson__course=course
    ).select_related(
        "lesson"
    )

    # -----------------------------------------------------
    # CREATE LESSON -> PROGRESS MAP
    # -----------------------------------------------------

    progress_map = {
        progress.lesson_id: progress
        for progress in progress_records
    }

    # -----------------------------------------------------
    # ATTACH PROGRESS TO EACH LESSON
    # -----------------------------------------------------

    completed_lessons = 0

    for lesson in lessons:

        lesson.progress = progress_map.get(
            lesson.id
        )

        if lesson.progress and lesson.progress.completed:

            completed_lessons += 1

    # -----------------------------------------------------
    # CALCULATE TOTAL LESSONS
    # -----------------------------------------------------

    total_lessons = len(lessons)

    # -----------------------------------------------------
    # CALCULATE PERCENTAGE
    # -----------------------------------------------------

    progress_percentage = 0

    if total_lessons > 0:

        progress_percentage = round(
            (
                completed_lessons /
                total_lessons
            ) * 100
        )

    # -----------------------------------------------------
    # RENDER
    # -----------------------------------------------------

    return render(
        request,
        "learning/course_progress.html",
        {
            "course": course,
            "enrollment": enrollment,
            "lessons": lessons,
            "total_lessons": total_lessons,
            "completed_lessons": completed_lessons,
            "progress_percentage": progress_percentage,
        }
    )
    
    
    
# =========================================================
# ADMIN - COURSE REVIEW
# =========================================================

@login_required
@user_passes_test(is_admin)
def admin_courses(request):

    courses = Course.objects.filter(
        status="PENDING"
    ).select_related(
        "category",
        "creator"
    ).order_by(
        "-created_at"
    )

    return render(
        request,
        "learning/admin_courses.html",
        {
            "courses": courses
        }
    )


# =========================================================
# ADMIN - COURSE REVIEW DETAIL
# =========================================================

@login_required
@user_passes_test(is_admin)
def admin_course_detail(request, course_id):

    course = get_object_or_404(
        Course.objects.select_related(
            "category",
            "creator"
        ).prefetch_related(
            "lessons"
        ),
        id=course_id,
        status="PENDING"
    )

    return render(
        request,
        "learning/admin_course_detail.html",
        {
            "course": course,
            "lessons": course.lessons.all()
        }
    )


# =========================================================
# ADMIN - APPROVE COURSE
# =========================================================

@login_required
@user_passes_test(is_admin)
@require_POST
def approve_course(request, course_id):

    course = get_object_or_404(
        Course,
        id=course_id,
        status="PENDING"
    )

    course.status = "APPROVED"

    course.save(
        update_fields=["status"]
    )

    messages.success(
        request,
        f'"{course.title}" has been approved successfully.'
    )

    return redirect(
        "admin_courses"
    )


# =========================================================
# ADMIN - REJECT COURSE
# =========================================================

@login_required
@user_passes_test(is_admin)
@require_POST
def reject_course(request, course_id):

    course = get_object_or_404(
        Course,
        id=course_id,
        status="PENDING"
    )

    reason = request.POST.get(
        "rejection_reason",
        ""
    ).strip()

    if not reason:

        messages.error(
            request,
            "Please provide a reason for rejecting the course."
        )

        return redirect(
            "admin_course_detail",
            course_id=course.id
        )

    course.status = "REJECTED"

    course.rejection_reason = reason

    course.save(
        update_fields=[
            "status",
            "rejection_reason"
        ]
    )

    messages.warning(
        request,
        f'"{course.title}" has been rejected.'
    )

    return redirect(
        "admin_courses"
    )
    
    
 # =========================================================
# MANAGE QUIZ
# =========================================================

@login_required
@user_passes_test(is_course_creator)
def manage_quiz(request, quiz_id):

    quiz = get_object_or_404(
        Quiz.objects.select_related(
            "lesson",
            "lesson__course"
        ),
        id=quiz_id
    )

    lesson = quiz.lesson
    course = lesson.course

    # -----------------------------------------------------
    # VERIFY COURSE OWNERSHIP
    # -----------------------------------------------------

 # VERIFY COURSE OWNERSHIP

    if (
        course.creator != request.user
        and request.user.role != "ADMIN"
        and not request.user.is_superuser
    ):

        messages.error(
            request,
            "You are not authorized to manage this quiz."
        )

        return redirect(
            "course_detail",
            slug=course.slug
        )

    # -----------------------------------------------------
    # GET QUESTIONS
    # -----------------------------------------------------

    questions = quiz.questions.all()

    return render(
        request,
        "learning/manage_quiz.html",
        {
            "quiz": quiz,
            "lesson": lesson,
            "course": course,
            "questions": questions,
        }
    )   
    
    
# =========================================================
# ADD QUESTION
# =========================================================

@login_required
@user_passes_test(is_course_creator)
def add_question(request, quiz_id):

    quiz = get_object_or_404(
        Quiz.objects.select_related(
            "lesson",
            "lesson__course"
        ),
        id=quiz_id
    )

    lesson = quiz.lesson
    course = lesson.course

    # -----------------------------------------------------
    # VERIFY COURSE OWNERSHIP
    # -----------------------------------------------------

    if course.creator != request.user:

        messages.error(
            request,
            "You are not authorized to manage this quiz."
        )

        return redirect(
            "course_detail",
            slug=course.slug
        )

    # -----------------------------------------------------
    # PREVENT MODIFICATION OF PENDING/APPROVED COURSES
    # -----------------------------------------------------

    if course.status in ["PENDING", "APPROVED"]:

        messages.warning(
            request,
            "Questions cannot be modified while the course is pending approval or approved."
        )

        return redirect(
            "manage_quiz",
            quiz_id=quiz.id
        )

    # -----------------------------------------------------
    # ADD QUESTION
    # -----------------------------------------------------

    if request.method == "POST":

        form = QuestionForm(request.POST)

        if form.is_valid():

            question = form.save(
                commit=False
            )

            question.quiz = quiz

            question.save()

            messages.success(
                request,
                "Question added successfully."
            )

            return redirect(
                "manage_quiz",
                quiz_id=quiz.id
            )

    else:

        form = QuestionForm()

    return render(
        request,
        "learning/add_question.html",
        {
            "form": form,
            "quiz": quiz,
            "lesson": lesson,
            "course": course,
        }
    )
    
    
# =========================================================
# EDIT QUESTION
# =========================================================

@login_required
@user_passes_test(is_course_creator)
def edit_question(request, question_id):

    question = get_object_or_404(
        Question.objects.select_related(
            "quiz",
            "quiz__lesson",
            "quiz__lesson__course"
        ),
        id=question_id
    )

    quiz = question.quiz
    lesson = quiz.lesson
    course = lesson.course

    # -----------------------------------------------------
    # VERIFY COURSE OWNERSHIP
    # -----------------------------------------------------

    if course.creator != request.user:

        messages.error(
            request,
            "You are not authorized to edit this question."
        )

        return redirect(
            "course_detail",
            slug=course.slug
        )

    # -----------------------------------------------------
    # PREVENT MODIFICATION OF PENDING/APPROVED COURSES
    # -----------------------------------------------------

    if course.status in ["PENDING", "APPROVED"]:

        messages.warning(
            request,
            "Questions cannot be modified while the course is pending approval or approved."
        )

        return redirect(
            "manage_quiz",
            quiz_id=quiz.id
        )

    # -----------------------------------------------------
    # EDIT QUESTION
    # -----------------------------------------------------

    if request.method == "POST":

        form = QuestionForm(
            request.POST,
            instance=question
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Question updated successfully."
            )

            return redirect(
                "manage_quiz",
                quiz_id=quiz.id
            )

    else:

        form = QuestionForm(
            instance=question
        )

    return render(
        request,
        "learning/edit_question.html",
        {
            "form": form,
            "question": question,
            "quiz": quiz,
            "lesson": lesson,
            "course": course,
        }
    )
# =========================================================
# DELETE QUESTION
# =========================================================

@login_required
@user_passes_test(is_course_creator)
def delete_question(request, question_id):

    question = get_object_or_404(
        Question.objects.select_related(
            "quiz",
            "quiz__lesson",
            "quiz__lesson__course"
        ),
        id=question_id
    )

    quiz = question.quiz
    lesson = quiz.lesson
    course = lesson.course

    # -----------------------------------------------------
    # VERIFY COURSE OWNERSHIP
    # -----------------------------------------------------

    if course.creator != request.user:

        messages.error(
            request,
            "You are not authorized to delete this question."
        )

        return redirect(
            "course_detail",
            slug=course.slug
        )

    # -----------------------------------------------------
    # PREVENT MODIFICATION OF PENDING/APPROVED COURSES
    # -----------------------------------------------------

    if course.status in ["PENDING", "APPROVED"]:

        messages.warning(
            request,
            "Questions cannot be deleted while the course is pending approval or approved."
        )

        return redirect(
            "manage_quiz",
            quiz_id=quiz.id
        )

    # -----------------------------------------------------
    # DELETE QUESTION
    # -----------------------------------------------------

    if request.method == "POST":

        question.delete()

        messages.success(
            request,
            "Question deleted successfully."

        )

    else:

        messages.warning(
            request,
            "Invalid request."
        )

    return redirect(
        "manage_quiz",
        quiz_id=quiz.id
    )
    
    
# =========================================================
# EDIT QUIZ
# =========================================================

@login_required
@user_passes_test(is_course_creator)
def edit_quiz(request, quiz_id):

    quiz = get_object_or_404(
        Quiz.objects.select_related(
            "lesson",
            "lesson__course"
        ),
        id=quiz_id
    )

    lesson = quiz.lesson
    course = lesson.course

    # -----------------------------------------------------
    # VERIFY COURSE OWNERSHIP
    # -----------------------------------------------------

    if course.creator != request.user:

        messages.error(
            request,
            "You are not authorized to edit this quiz."
        )

        return redirect(
            "course_detail",
            slug=course.slug
        )

    # -----------------------------------------------------
    # PREVENT MODIFICATION OF PENDING/APPROVED COURSES
    # -----------------------------------------------------

    if course.status in ["PENDING", "APPROVED"]:

        messages.warning(
            request,
            "Quizzes cannot be modified while the course is pending approval or approved."
        )

        return redirect(
            "manage_quiz",
            quiz_id=quiz.id
        )

    # -----------------------------------------------------
    # EDIT QUIZ
    # -----------------------------------------------------

    if request.method == "POST":

        form = QuizForm(
            request.POST,
            instance=quiz
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Quiz updated successfully."
            )

            return redirect(
                "manage_quiz",
                quiz_id=quiz.id
            )

    else:

        form = QuizForm(
            instance=quiz
        )

    return render(
        request,
        "learning/edit_quiz.html",
        {
            "form": form,
            "quiz": quiz,
            "lesson": lesson,
            "course": course,
        }
    )    
    
    
    

# =========================================================
# DELETE QUIZ
# =========================================================

@login_required
@user_passes_test(is_course_creator)
def delete_quiz(request, quiz_id):

    quiz = get_object_or_404(
        Quiz.objects.select_related(
            "lesson",
            "lesson__course"
        ),
        id=quiz_id
    )

    lesson = quiz.lesson
    course = lesson.course

    # -----------------------------------------------------
    # VERIFY COURSE OWNERSHIP
    # -----------------------------------------------------

    if course.creator != request.user:

        messages.error(
            request,
            "You are not authorized to delete this quiz."
        )

        return redirect(
            "course_detail",
            slug=course.slug
        )

    # -----------------------------------------------------
    # PREVENT MODIFICATION OF PENDING/APPROVED COURSES
    # -----------------------------------------------------

    if course.status in ["PENDING", "APPROVED"]:

        messages.warning(
            request,
            "Quizzes cannot be deleted while the course is pending approval or approved."
        )

        return redirect(
            "manage_quiz",
            quiz_id=quiz.id
        )

    # -----------------------------------------------------
    # ONLY DELETE THROUGH POST
    # -----------------------------------------------------

    if request.method != "POST":

        messages.warning(
            request,
            "Invalid request."
        )

        return redirect(
            "manage_quiz",
            quiz_id=quiz.id
        )

    # -----------------------------------------------------
    # DELETE QUIZ
    # -----------------------------------------------------

    quiz.delete()

    messages.success(
        request,
        "Quiz deleted successfully."
    )

    return redirect(
        "manage_course",
        course_id=course.id
    )    
    
    



# =========================================================
# MY CERTIFICATES
# =========================================================

@login_required
def my_certificates(request):

    certificates = Certificate.objects.filter(
        enrollment__user=request.user
    ).select_related(
        "enrollment",
        "enrollment__course"
    ).order_by(
        "-issued_at"
    )

    return render(
        request,
        "learning/my_certificates.html",
        {
            "certificates": certificates
        }
    )
    
    

# =========================================================
# CERTIFICATE DETAIL
# =========================================================

@login_required
def certificate_detail(request, certificate_id):

    certificate = get_object_or_404(
        Certificate.objects.select_related(
            "enrollment",
            "enrollment__course",
            "enrollment__course__creator"
        ),
        certificate_id=certificate_id
    )

    enrollment = certificate.enrollment
    course = enrollment.course

    # -----------------------------------------------------
    # ONLY THE CERTIFICATE OWNER CAN VIEW IT
    # -----------------------------------------------------

    if enrollment.user != request.user:

        messages.error(
            request,
            "You are not authorized to view this certificate."
        )

        return redirect(
            "my_certificates"
        )

    # -----------------------------------------------------
    # DISPLAY CERTIFICATE
    # -----------------------------------------------------

    return render(
        request,
        "learning/certificate_detail.html",
        {
            "certificate": certificate,
            "enrollment": enrollment,
            "course": course,
        }
    )
    
    
# =========================================================
# GENERATE CERTIFICATE PDF
# =========================================================

def generate_certificate_pdf(certificate):

    enrollment = certificate.enrollment
    course = enrollment.course
    user = enrollment.user

    # -----------------------------------------------------
    # LEARNER NAME
    # -----------------------------------------------------

    learner_name = user.get_full_name()

    if not learner_name:
        learner_name = user.username

    # -----------------------------------------------------
    # CREATE PDF IN MEMORY
    # -----------------------------------------------------

    buffer = BytesIO()

    page_width, page_height = landscape(A4)

    pdf = canvas.Canvas(
        buffer,
        pagesize=(page_width, page_height)
    )

    # -----------------------------------------------------
    # BORDER
    # -----------------------------------------------------

    margin = 30

    pdf.setLineWidth(3)

    pdf.rect(
        margin,
        margin,
        page_width - (margin * 2),
        page_height - (margin * 2)
    )

    # Inner border

    pdf.setLineWidth(1)

    pdf.rect(
        margin + 10,
        margin + 10,
        page_width - (margin * 2) - 20,
        page_height - (margin * 2) - 20
    )

    # -----------------------------------------------------
    # AWINLINK
    # -----------------------------------------------------

    pdf.setFont(
        "Helvetica-Bold",
        28
    )

    pdf.drawCentredString(
        page_width / 2,
        page_height - 80,
        "AWINLINK"
    )

    pdf.setFont(
        "Helvetica",
        11
    )

    pdf.drawCentredString(
        page_width / 2,
        page_height - 100,
        "Talent & Learning Platform"
    )

    # -----------------------------------------------------
    # CERTIFICATE TITLE
    # -----------------------------------------------------

    pdf.setFont(
        "Helvetica-Bold",
        30
    )

    pdf.drawCentredString(
        page_width / 2,
        page_height - 155,
        "CERTIFICATE OF COMPLETION"
    )

    # -----------------------------------------------------
    # PRESENTED TO
    # -----------------------------------------------------

    pdf.setFont(
        "Helvetica",
        14
    )

    pdf.drawCentredString(
        page_width / 2,
        page_height - 205,
        "This certificate is proudly presented to"
    )

    # -----------------------------------------------------
    # LEARNER
    # -----------------------------------------------------

    pdf.setFont(
        "Helvetica-Bold",
        26
    )

    pdf.drawCentredString(
        page_width / 2,
        page_height - 245,
        learner_name
    )

    # -----------------------------------------------------
    # COURSE MESSAGE
    # -----------------------------------------------------

    pdf.setFont(
        "Helvetica",
        14
    )

    pdf.drawCentredString(
        page_width / 2,
        page_height - 290,
        "for successfully completing the course"
    )

    # -----------------------------------------------------
    # COURSE TITLE
    # -----------------------------------------------------

    pdf.setFont(
        "Helvetica-Bold",
        22
    )

    pdf.drawCentredString(
        page_width / 2,
        page_height - 330,
        course.title
    )

    # -----------------------------------------------------
    # ISSUE DATE
    # -----------------------------------------------------

    pdf.setFont(
        "Helvetica",
        11
    )

    issued_date = certificate.issued_at.strftime(
        "%B %d, %Y"
    )

    pdf.drawCentredString(
        page_width / 2,
        page_height - 380,
        f"Issued on {issued_date}"
    )

    # -----------------------------------------------------
    # CERTIFICATE ID
    # -----------------------------------------------------

    pdf.setFont(
        "Helvetica",
        10
    )

    pdf.drawCentredString(
        page_width / 2,
        75,
        f"Certificate ID: {certificate.certificate_id}"
    )

    # -----------------------------------------------------
    # ISSUED BY
    # -----------------------------------------------------

    pdf.drawString(
        80,
        100,
        "Issued by"
    )

    pdf.setFont(
        "Helvetica-Bold",
        11
    )

    pdf.drawString(
        80,
        85,
        "Awinlink"
    )

    # -----------------------------------------------------
    # STATUS
    # -----------------------------------------------------

    pdf.setFont(
        "Helvetica",
        10
    )

    pdf.drawRightString(
        page_width - 80,
        100,
        "Certificate Status"
    )

    pdf.setFont(
        "Helvetica-Bold",
        11
    )

    pdf.drawRightString(
        page_width - 80,
        85,
        "COMPLETED"
    )

    # -----------------------------------------------------
    # FINISH
    # -----------------------------------------------------

    pdf.showPage()
    pdf.save()

    buffer.seek(0)

    return buffer



# =========================================================
# DOWNLOAD CERTIFICATE PDF
# =========================================================


@login_required
def download_certificate(request, certificate_id):

    certificate = get_object_or_404(
        Certificate.objects.select_related(
            "enrollment",
            "enrollment__course"
        ),
        certificate_id=certificate_id
    )

    # -----------------------------------------------------
    # VERIFY OWNERSHIP
    # -----------------------------------------------------

    if certificate.enrollment.user != request.user:

        messages.error(
            request,
            "You are not authorized to download this certificate."
        )

        return redirect(
            "my_certificates"
        )

    # -----------------------------------------------------
    # CERTIFICATE PDF MUST EXIST
    # -----------------------------------------------------

    if not certificate.pdf:

        certificate = generate_certificate(
            certificate.enrollment
        )

    # -----------------------------------------------------
    # RETURN SAVED PDF
    # -----------------------------------------------------

    response = FileResponse(
        certificate.pdf.open("rb"),
        content_type="application/pdf"
    )

    response["Content-Disposition"] = (
        f'attachment; filename="{certificate.certificate_id}.pdf"'
    )

    return response




# =========================================================
# VIEW CERTIFICATE
# =========================================================

@login_required
def view_certificate(request, certificate_id):

    certificate = get_object_or_404(
        Certificate.objects.select_related(
            "enrollment",
            "enrollment__course",
            "enrollment__user"
        ),
        certificate_id=certificate_id,
        enrollment__user=request.user
    )

    return render(
        request,
        "learning/certificate_detail.html",
        {
            "certificate": certificate,
            "enrollment": certificate.enrollment,
            "course": certificate.enrollment.course,
        }
    )


# =========================================================
# VERIFY CERTIFICATE
# =========================================================

def verify_certificate(request, certificate_id=None):

    certificate = None

    if certificate_id:

        certificate = Certificate.objects.filter(
            certificate_id=certificate_id
        ).select_related(
            "enrollment",
            "enrollment__user",
            "enrollment__course",
            "enrollment__course__creator"
        ).first()

        if not certificate:

            messages.error(
                request,
                "The certificate ID entered is invalid or does not exist."
            )

    elif request.method == "POST":

        entered_id = request.POST.get(
            "certificate_id",
            ""
        ).strip()

        if entered_id:

            return redirect(
                "verify_certificate",
                certificate_id=entered_id
            )

        messages.error(
            request,
            "Please enter a certificate ID."

        )

    return render(
        request,
        "learning/verify_certificate.html",
        {
            "certificate": certificate,
        }
    )
    
# =========================================================
# MY QUIZ ATTEMPTS
# =========================================================

@login_required
def my_quiz_attempts(request):

    attempts = QuizAttempt.objects.filter(
        enrollment__user=request.user
    ).select_related(
        "quiz",
        "quiz__lesson",
        "quiz__lesson__course"
    ).order_by(
        "-attempted_at"
    )

    return render(
        request,
        "learning/my_quiz_attempts.html",
        {
            "attempts": attempts
        }
    )    


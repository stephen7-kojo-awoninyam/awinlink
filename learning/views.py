from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.db.models import Avg, Max
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
import uuid
from io import BytesIO
from django.core.files.base import ContentFile
from django.http import FileResponse, HttpResponse
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

from .utils import generate_certificate
from .services import LearningService
from .curriculum import group_course_lessons
from .classroom_learning import visible_learning_sessions

from .models import (
    LearningCategory,
    Course,
    CourseModule,
    Lesson,
    Enrollment,
    LessonProgress,
    CourseReview,
    CourseLike,
    CourseComment,
    Quiz,
    Question,
    QuizAttempt,
    Certificate
)

from .forms import (
    LearningCategoryForm,
    CourseForm,
    LessonForm,
    CourseModuleForm,
    CourseReviewForm,
    QuizForm,
    QuestionForm,
  
    
)
from recommendations.unified import (
    UnifiedRecommendationService,
    unified_recommendations_enabled,
)


# =========================================================
# LEARNING ROLE PERMISSIONS
# =========================================================

def is_course_creator(user):
    return LearningService.can_create_course(user)


def is_admin(user):
    """
    Users who are allowed to perform Learning administration.
    """
    return (
        user.is_authenticated
        and user.role == "ADMIN"
    )


def _display_learning_progress(enrollment):
    """Read-only lesson progress for discovery/detail presentation."""
    enrollment.total_lessons = enrollment.course.lessons.count()
    enrollment.completed_lessons = enrollment.lesson_progress.filter(
        completed=True, lesson__course_id=enrollment.course_id,
    ).count()
    enrollment.progress_percentage = round(100 * enrollment.completed_lessons / enrollment.total_lessons) if enrollment.total_lessons else 0
    return enrollment


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

    if unified_recommendations_enabled() and getattr(request.user, "talent_profile", None):
        filtered_courses = list(courses)
        unified_rows = UnifiedRecommendationService().recommend_learning(
            request.user,
            limit=len(filtered_courses),
            candidates=filtered_courses,
        )
        courses = []
        for row in unified_rows:
            course = row["item"]
            course.recommendation_score = row["score"]
            course.matched_topics = row["matched_topics"]
            course.recommendation_explanation = row["explanation"]
            courses.append(course)

    continue_enrollments = [
        _display_learning_progress(enrollment)
        for enrollment in Enrollment.objects.filter(
            user=request.user, course__status='APPROVED', completed=False,
        ).select_related('course', 'course__creator', 'course__category').order_by('-enrolled_at', '-pk')[:3]
    ]

    return render(
        request,
        "learning/course_list.html",
        {
            "courses": courses,
            "categories": categories,
            "continue_enrollments": continue_enrollments,
        }
    )


# =========================================================
# COURSE DETAIL
# =========================================================

@login_required
@require_POST
def like_course(request, course_id):
    course = get_object_or_404(Course, id=course_id, status="APPROVED")
    like, created = CourseLike.objects.get_or_create(user=request.user, course=course)
    liked = True

    if not created:
        like.delete()
        liked = False

    if request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("accept", "").lower():
        return JsonResponse({
            "status": "success",
            "liked": liked,
            "count": course.likes.count(),
        })

    return redirect("course_detail", slug=course.slug)


@login_required
def add_course_comment(request, course_id):
    course = get_object_or_404(Course, id=course_id, status="APPROVED")

    if request.method == "POST":
        text = request.POST.get("text", "").strip()
        if text:
            comment = CourseComment.objects.create(user=request.user, course=course, text=text)
            if request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("accept", "").lower():
                return JsonResponse({
                    "status": "success",
                    "comment": {
                        "user": comment.user.get_full_name() or comment.user.username,
                        "text": comment.text,
                        "created_at": comment.created_at.strftime("%b %d, %Y %H:%M"),
                    },
                    "count": course.comments.count(),
                })
            return redirect("course_detail", slug=course.slug)

    if request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("accept", "").lower():
        return JsonResponse({"status": "error", "message": "Empty comment."}, status=400)

    return redirect("course_detail", slug=course.slug)


@login_required
def course_detail(request, slug):

    course = get_object_or_404(Course.objects.select_related("category", "creator"), slug=slug)
    preview = course.status != "APPROVED"
    if preview and course.creator_id != request.user.pk and request.user.role != "ADMIN":
        from django.http import Http404
        raise Http404

    lessons, curriculum_sections = group_course_lessons(course, course.lessons.all().order_by("order", "pk").select_related("quiz", "module"))

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
    if enrollment:
        _display_learning_progress(enrollment)

    return render(
        request,
        "learning/course_detail.html",
        {
            "course": course,
            "lessons": lessons,
            "modules": course.modules.all(),
            "curriculum_sections": curriculum_sections,
            "learning_live_sessions": visible_learning_sessions(request.user, course.pk),
            "enrollment": enrollment,
            "reviews": reviews,
            "average_rating": average_rating,
            "total_reviews": total_reviews,
            "preview": preview,
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
            course.is_free = True

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

        form = CourseForm(creator=request.user)

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
@require_POST
def enroll_course(request, course_id):
    course = get_object_or_404(Course, id=course_id, status='APPROVED')
    try:
        enrollment, created = LearningService.enroll(course, request.user)
    except ValueError as error:
        messages.warning(request, str(error))
    else:
        messages.success(request, f'You have enrolled in {course.title}.' if created else 'You are already enrolled in this course.')
    return redirect('course_detail', slug=course.slug)


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

    enrollment = Enrollment.objects.filter(user=request.user, course=lesson.course).first()
    preview = enrollment is None
    if preview and lesson.course.creator_id != request.user.pk and request.user.role != "ADMIN":
        from django.http import Http404
        raise Http404

    progress = None
    progress_by_lesson = {}
    if enrollment:
        progress, _ = LessonProgress.objects.get_or_create(enrollment=enrollment, lesson=lesson)
        progress_by_lesson = {
            item.lesson_id: item
            for item in LessonProgress.objects.filter(enrollment=enrollment, lesson__course=lesson.course)
        }
    lessons, curriculum_sections = group_course_lessons(lesson.course, lesson.course.lessons.all().order_by("order", "pk").select_related("quiz", "module"))
    for item in lessons:
        item.workspace_progress = progress_by_lesson.get(item.id)
    quiz = getattr(lesson, "quiz", None)
    latest_attempt = None
    if quiz and enrollment:
        latest_attempt = QuizAttempt.objects.filter(enrollment=enrollment, quiz=quiz).first()

    return render(
        request,
        "learning/lesson_detail.html",
        {
            "lesson": lesson,
            "course": lesson.course,
            "enrollment": enrollment,
            "progress": progress,
            "lessons": lessons,
            "curriculum_sections": curriculum_sections,
            "learning_live_sessions": visible_learning_sessions(request.user, lesson.course_id, lesson_id=lesson.pk),
            "quiz": quiz,
            "latest_attempt": latest_attempt,
            "preview": preview,
            "course_progress_percent": round(
                sum(1 for item in progress_by_lesson.values() if item.completed)
                / max(len(lessons), 1) * 100
            ),
        }
    )



# =========================================================
# COMPLETE LESSON
# =========================================================

@login_required
def complete_lesson(request, lesson_id):
    lesson = get_object_or_404(Lesson.objects.select_related('course'), id=lesson_id)
    if request.method != 'POST':
        return redirect(lesson_detail, lesson_id=lesson.id)
    try:
        progress, certificate = LearningService.set_lesson_completion(lesson, request.user)
    except ValueError as error:
        messages.warning(request, str(error))
        if hasattr(lesson, 'quiz'):
            return redirect('take_quiz', quiz_id=lesson.quiz.id)
        return redirect(lesson_detail, lesson_id=lesson.id)
    try:
        certificate = LearningService.ensure_certificate_pdf(certificate, writer=generate_certificate)
    except Exception:
        messages.warning(request, 'Progress saved; certificate PDF is temporarily unavailable. Retry completion to generate it.')
    else:
        messages.success(request, 'Congratulations! You have completed the course and earned your certificate.' if certificate else 'Lesson marked as complete.')
    return redirect(lesson_detail, lesson_id=lesson.id)
    
    
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
            my_courses
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
                my_courses
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
@require_POST
def submit_course(request, course_id):
    course = get_object_or_404(Course, id=course_id, creator=request.user)
    try:
        LearningService.submit_course(course, request.user)
    except (PermissionError, ValueError) as error:
        messages.warning(request, str(error))
    else:
        messages.success(request, 'Course submitted for approval.')
    return redirect(my_courses)


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
            my_courses
        )

    # -----------------------------------------------------
    # ADD LESSON
    # -----------------------------------------------------

    if request.method == "POST":

        form = LessonForm(request.POST, request.FILES, course=course)

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

        form = LessonForm(initial={"order": next_order}, course=course)

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

    lessons, curriculum_sections = group_course_lessons(course, course.lessons.all().order_by("order", "pk").select_related("quiz", "module").prefetch_related("quiz__questions"))
    progress_lesson_ids = set(LessonProgress.objects.filter(lesson__course=course).values_list("lesson_id", flat=True))
    attempt_lesson_ids = set(QuizAttempt.objects.filter(quiz__lesson__course=course).values_list("quiz__lesson_id", flat=True))
    for lesson in lessons:
        lesson.has_learner_history = lesson.id in progress_lesson_ids or lesson.id in attempt_lesson_ids

    return render(
        request,
        "learning/manage_course.html",
        {
            "course": course,
            "lessons": lessons,
            "modules": course.modules.all(),
            "curriculum_sections": curriculum_sections,
            "submission_checklist": LearningService.submission_checklist(course),
        }
    )


@login_required
@user_passes_test(is_course_creator)
@require_POST
@transaction.atomic
def create_course_module(request, course_id):
    course = get_object_or_404(Course.objects.select_for_update(), pk=course_id, creator=request.user)
    if course.status not in {'DRAFT', 'REJECTED'}:
        messages.warning(request, 'Course sections can only be changed while a course is editable.')
        return redirect('manage_course', course_id=course.pk)
    data = request.POST.copy()
    if not data.get('order'):
        data['order'] = (course.modules.aggregate(last=Max('order'))['last'] or 0) + 1
    form = CourseModuleForm(data)
    if form.is_valid():
        module = form.save(commit=False)
        module.course = course
        module.save()
        messages.success(request, 'Course section added.')
    else:
        messages.error(request, 'Enter a valid section title and order.')
    return redirect('manage_course', course_id=course.pk)


@login_required
@user_passes_test(is_course_creator)
@require_POST
@transaction.atomic
def edit_course_module(request, module_id):
    module = get_object_or_404(CourseModule.objects.select_related('course').select_for_update(), pk=module_id, course__creator=request.user)
    course = Course.objects.select_for_update().get(pk=module.course_id)
    if course.status not in {'DRAFT', 'REJECTED'}:
        messages.warning(request, 'Course sections can only be changed while a course is editable.')
        return redirect('manage_course', course_id=course.pk)
    form = CourseModuleForm(request.POST, instance=module)
    if form.is_valid():
        form.save()
        messages.success(request, 'Course section updated.')
    else:
        messages.error(request, 'Enter a valid section title and order.')
    return redirect('manage_course', course_id=course.pk)


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

        form = LessonForm(request.POST, request.FILES, instance=lesson, course=course)

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

        form = LessonForm(instance=lesson, course=course)

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

        if LessonProgress.objects.filter(lesson=lesson).exists() or QuizAttempt.objects.filter(quiz__lesson=lesson).exists():
            messages.warning(request, "This lesson has learner history and cannot be deleted.")
            return redirect("manage_course", course_id=course.id)

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
    quiz = get_object_or_404(Quiz.objects.select_related('lesson__course'), id=quiz_id)
    lesson, course = quiz.lesson, quiz.lesson.course
    LearningService.require_quiz_access(request.user, course)
    enrollment = get_object_or_404(Enrollment, user=request.user, course=course)
    questions = list(quiz.questions.all().order_by('id'))
    if not questions:
        messages.warning(request, 'This quiz does not have any questions yet.')
        return redirect(lesson_detail, lesson_id=lesson.id)
    if request.method == 'POST':
        answers = {key.removeprefix('question_'): value for key, value in request.POST.items() if key.startswith('question_')}
        try:
            attempt = LearningService.record_quiz_attempt(quiz, request.user, answers)
        except ValueError as error:
            messages.error(request, str(error))
        else:
            return render(request, 'learning/quiz_result.html', {
                'quiz': quiz, 'lesson': lesson, 'course': course, 'enrollment': enrollment,
                'attempt': attempt, 'score': attempt.score, 'total_questions': attempt.total_questions,
                'percentage': attempt.percentage, 'passed': attempt.passed,
                'question_feedback': attempt.question_feedback,
            })
    return render(request, 'learning/take_quiz.html', {'quiz': quiz, 'lesson': lesson, 'course': course,
        'questions': questions, 'enrollment': enrollment})

   

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

    lessons, curriculum_sections = group_course_lessons(course, course.lessons.all().order_by('order', 'pk').select_related('module'))

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
            "curriculum_sections": curriculum_sections,
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
    course = get_object_or_404(Course, id=course_id, status='PENDING')
    try:
        LearningService.approve_course(course)
    except ValueError as error:
        messages.warning(request, str(error))
        return redirect('admin_course_detail', course_id=course.id)
    messages.success(request, f'"{course.title}" has been approved successfully.')
    return redirect('admin_courses')


# =========================================================
# ADMIN - REJECT COURSE
# =========================================================

@login_required
@user_passes_test(is_admin)
@require_POST
def reject_course(request, course_id):
    course = get_object_or_404(Course, id=course_id, status='PENDING')
    try:
        LearningService.reject_course(course, request.POST.get('rejection_reason', ''))
    except ValueError as error:
        messages.error(request, str(error))
        return redirect('admin_course_detail', course_id=course.id)
    messages.warning(request, f'"{course.title}" has been rejected.')
    return redirect('admin_courses')
    
    
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

        if QuizAttempt.objects.filter(quiz=quiz).exists():
            messages.warning(request, "This quiz has learner attempts and cannot be deleted.")
            return redirect("manage_quiz", quiz_id=quiz.id)

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

    if QuizAttempt.objects.filter(quiz=quiz).exists():
        messages.warning(request, "This quiz has learner attempts and cannot be deleted.")
        return redirect("manage_quiz", quiz_id=quiz.id)

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
            my_certificates
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
            my_certificates
        )

    # -----------------------------------------------------
    # CERTIFICATE PDF MUST EXIST
    # -----------------------------------------------------

    if not certificate.pdf:

        try:
            certificate = LearningService.ensure_certificate_pdf(certificate, writer=generate_certificate)
        except Exception:
            return HttpResponse('Certificate PDF is temporarily unavailable. Please retry.', status=503)

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


from django.core.exceptions import PermissionDenied
from django.db.models import Q
from rest_framework.permissions import BasePermission

from accounts.age_policy import age_access_allowed
from accounts.age_safety import approved_authorizations, cutoff, minor
from accounts.models import GuardianCoursePermission, User


def courses_for(user, query, *, live=False):
    current = User.objects.filter(pk=getattr(user, "pk", None), is_active=True).first()
    if current is None or not age_access_allowed(current):
        return query.none()
    if minor(current):
        today = cutoff(0)
        birth = current.date_of_birth
        years = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
        query = query.filter(minimum_age__lte=years)
    if current.age_group == "CHILD":
        grants = GuardianCoursePermission.objects.filter(authorization__in=approved_authorizations().filter(child=current))
        if live:
            grants = grants.filter(allow_live=True)
        query = query.filter(pk__in=grants.values("course_id"))
    return query


def course_allowed(user, course, *, live=False):
    from .models import Course
    current = User.objects.filter(pk=getattr(user, "pk", None), is_active=True).first()
    if current is None or not courses_for(current, Course.objects.filter(pk=course.pk), live=live).exists():
        return False
    if live and current.age_group == "CHILD":
        return GuardianCoursePermission.objects.filter(authorization__in=approved_authorizations().filter(child=current),
                                                       course=course, allow_live=True).exists()
    return True


def require_course_access(user, course, *, live=False):
    if not course_allowed(user, course, live=live):
        raise PermissionDenied("This course or live classroom requires age eligibility and guardian approval.")


class AgeSafeLearningPermission(BasePermission):
    def has_permission(self, request, view):
        from .models import Course, Lesson, Quiz, Question, Enrollment, Certificate
        args = view.kwargs
        course_id = args.get("course_id")
        lookups = {"lesson_id": (Lesson, "course_id"), "quiz_id": (Quiz, "lesson__course_id"),
                   "question_id": (Question, "quiz__lesson__course_id"), "enrollment_id": (Enrollment, "course_id"),
                   "certificate_id": (Certificate, "enrollment__course_id")}
        for key, (model, field) in lookups.items():
            if key in args:
                lookup = "certificate_id" if key == "certificate_id" and not str(args[key]).isdigit() else "pk"
                course_id = model.objects.filter(**{lookup: args[key]}).values_list(field, flat=True).first()
        course = Course.objects.filter(pk=course_id).first() if course_id else None
        if course:
            require_course_access(request.user, course)
        return True

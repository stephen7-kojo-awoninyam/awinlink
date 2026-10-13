"""Read-only helpers for learning navigation and existing role rules."""
from django import template
from django.urls import reverse
from learning import views
from learning.views import is_course_creator

register = template.Library()


@register.simple_tag
def learning_url(view_name, *args):
    """Resolve the existing web callback when an API reuses its URL name."""
    allowed = {"my_courses", "lesson_detail", "course_progress", "my_certificates", "my_quiz_attempts"}
    if view_name not in allowed:
        raise ValueError("Unknown learning web view")
    return reverse(getattr(views, view_name), args=args)


@register.simple_tag
def learning_creator(user):
    return is_course_creator(user)


@register.simple_tag
def course_liked(course, user):
    return user.is_authenticated and course.likes.filter(user=user).exists()


@register.simple_tag
def adjacent_lessons(lessons, lesson):
    items = list(lessons)
    for index, item in enumerate(items):
        if item.pk == lesson.pk:
            return {
                "previous": items[index - 1] if index else None,
                "next": items[index + 1] if index + 1 < len(items) else None,
            }
    return {"previous": None, "next": None}

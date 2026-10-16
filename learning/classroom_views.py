from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from .classroom_api_views import visible_classrooms
from .models import LiveSession


@login_required
def directory(request):
    return render(request, "learning/classrooms.html", {"user": request.user})


@login_required
def classroom(request, session_id):
    session = get_object_or_404(LiveSession.objects.filter(classroom__in=visible_classrooms(request.user)), pk=session_id)
    return render(request, "learning/classroom.html", {"session": session, "user": request.user})

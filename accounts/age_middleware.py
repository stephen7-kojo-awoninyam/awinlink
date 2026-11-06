from django.http import JsonResponse
from django.shortcuts import render

from .age_policy import age_access_allowed, PENDING_MESSAGE


class AgeAccountMiddleware:
    """Protect existing browser sessions too; JWT access is checked by authentication."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated and not age_access_allowed(user) and request.path != "/accounts/logout/":
            # Standalone safety intake does not authorize account access or fetch private targets.
            if request.path == '/child-safety/report/' and request.method in {'GET', 'HEAD', 'POST'}:
                return self.get_response(request)
            # Legal information and request channels remain readable without
            # lifting the account restriction or allowing any mutation.
            if request.method in {"GET", "HEAD"} and request.path in {
                "/privacy/", "/terms/", "/community-guidelines/", "/child-safety/", "/support/", "/delete-account/"
            }:
                return self.get_response(request)
            if request.path.startswith("/api/"):
                return JsonResponse({"guardian_approval_required": True, "detail": PENDING_MESSAGE}, status=403)
            return render(request, "accounts/guardian_pending.html", status=403)
        return self.get_response(request)

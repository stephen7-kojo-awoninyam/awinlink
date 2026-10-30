"""The default admin registry, with the existing shared login attempt budget."""
from django.contrib.admin import AdminSite
from django.contrib.auth.decorators import login_not_required
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters


class SecureAdminSite(AdminSite):
    @method_decorator(never_cache)
    @method_decorator(sensitive_post_parameters())
    @method_decorator(csrf_protect)
    @login_not_required
    def login(self, request, extra_context=None):
        if request.method == 'POST':
            from rest_framework.exceptions import Throttled
            from .security import AuthenticationUnavailable, enforce_auth_limit
            try:
                enforce_auth_limit(request, 'login', request.POST.get('username', ''))
            except (Throttled, AuthenticationUnavailable) as error:
                response = JsonResponse({'detail': str(error.detail)}, status=error.status_code)
                if isinstance(error, Throttled):
                    response['Retry-After'] = str(error.wait)
                return response
        return super().login(request, extra_context=extra_context)

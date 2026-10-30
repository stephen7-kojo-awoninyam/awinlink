from django.contrib.auth.views import LoginView


class SharedLimitLoginView(LoginView):
    """Keep Django's CSRF/session/redirect behavior on ancillary sign-in pages."""
    def post(self, request, *args, **kwargs):
        from .views import authentication_limit_response
        response = authentication_limit_response(request, 'login')
        if response is not None:
            return response
        return super().post(request, *args, **kwargs)

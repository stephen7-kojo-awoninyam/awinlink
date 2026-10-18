from django.contrib.auth import views as auth_views
from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import HttpResponseRedirect
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters

from .recovery import RecoveryForm, RecoverySetPasswordForm, RecoveryUnavailable, allow_request, allow_confirmation, send_recovery


class PrivateRecoveryResponse:
    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        response['Referrer-Policy'] = 'no-referrer'
        return response


@method_decorator([never_cache, sensitive_post_parameters()], name='dispatch')
class PasswordResetView(PrivateRecoveryResponse, auth_views.PasswordResetView):
    form_class = RecoveryForm
    template_name = 'accounts/password_reset.html'
    success_url = '/accounts/password-reset/done/'

    def post(self, request, *args, **kwargs):
        try:
            if not allow_request(request):
                return self.limited(429, 'Too many requests. Please try again later.')
        except RecoveryUnavailable:
            return self.limited(503, 'Password recovery is temporarily unavailable. Please try again later.')
        return super().post(request, *args, **kwargs)

    def limited(self, status, message):
        form = self.get_form()
        form.add_error(None, message)
        response = self.render_to_response(self.get_context_data(form=form), status=status)
        response['Retry-After'] = '3600' if status == 429 else '60'
        return response

    def form_valid(self, form):
        try:
            send_recovery(form)
        except RecoveryUnavailable:
            return self.limited(503, 'Password recovery is temporarily unavailable. Please try again later.')
        return HttpResponseRedirect(self.success_url)


@method_decorator([transaction.atomic, never_cache, sensitive_post_parameters()], name='dispatch')
class PasswordResetConfirmView(PrivateRecoveryResponse, auth_views.PasswordResetConfirmView):
    form_class = RecoverySetPasswordForm
    template_name = 'accounts/password_reset_confirm.html'
    success_url = '/accounts/reset/done/'

    def dispatch(self, request, *args, **kwargs):
        try:
            if request.method == 'POST' and not allow_confirmation(request):
                response = self.render_to_response({'validlink': False, 'recovery_error': 'Too many reset attempts. Please try again later.'}, status=429)
                response['Retry-After'] = '900'
                response['Referrer-Policy'] = 'no-referrer'
                return response
        except RecoveryUnavailable:
            response = self.render_to_response({'validlink': False, 'recovery_error': 'Password recovery is temporarily unavailable. Please try again later.'}, status=503)
            response['Referrer-Policy'] = 'no-referrer'
            return response
        return super().dispatch(request, *args, **kwargs)

    def get_user(self, uidb64):
        user = super().get_user(uidb64)
        if user is not None and self.request.method == 'POST':
            user = get_user_model().objects.select_for_update().filter(pk=user.pk, is_active=True).first()
        if user is None or not user.is_active or not user.has_usable_password():
            return None
        return user

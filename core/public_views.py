from django.conf import settings
from django.contrib.auth import get_user_model, logout
from django.db import transaction
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from accounts.legal import TERMS_VERSION


@require_http_methods(['GET', 'HEAD', 'POST'])
def public_page(request, page):
    error = ''
    deleted = False
    if request.method == 'POST':
        if page != 'delete-account':
            from django.http import HttpResponseNotAllowed
            return HttpResponseNotAllowed(['GET', 'HEAD'])
        if not request.user.is_authenticated:
            error = 'Sign in before deleting your account.'
        else:
            with transaction.atomic():
                user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
                from organizations.models import Organization
                if not user.check_password(request.POST.get('password', '')):
                    error = 'Enter your current password.'
                elif request.POST.get('confirm') != 'yes':
                    error = 'Confirm permanent account deletion.'
                elif Organization.objects.filter(user=user).exists():
                    error = 'Transfer organization ownership in Awinlink before deleting your account.'
                else:
                    user.delete()
                    logout(request)
                    deleted = True
    response = render(request, 'core/public_page.html', {
        'page': page, 'error': error, 'deleted': deleted,
        'support_email': settings.AWINLINK_SUPPORT_EMAIL,
        'operator': settings.AWINLINK_LEGAL_OPERATOR,
        'terms_version': TERMS_VERSION,
    }, status=400 if error else 200)
    response['Cache-Control'] = 'no-store'
    return response

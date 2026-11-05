from django.contrib.auth import logout
from django.db import transaction
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from accounts.legal import TERMS_VERSION
from .legal import legal_context
from accounts.age_policy import age_access_allowed


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
                from accounts.deletion import delete_own_account, DeletionDenied
                if request.POST.get('confirm') != 'yes':
                    error = 'Confirm permanent account deletion.'
                else:
                    try:
                        if request.POST.get('auth_method') == 'google':
                            delete_own_account(user_id=request.user.pk, browser_state=request.session.get('google_delete_verified', ''))
                        else:
                            delete_own_account(user_id=request.user.pk, password=request.POST.get('password'))
                    except DeletionDenied as exc:
                        error = str(exc)
                    else:
                        logout(request)
                        deleted = True
    response = render(request, 'core/public_page.html', {
        'page': page, 'error': error, 'deleted': deleted,
        **legal_context(),
        'terms_version': TERMS_VERSION,
        'google_linked': request.user.is_authenticated and hasattr(request.user, 'google_identity'),
        'google_delete_ready': bool(request.session.get('google_delete_verified')),
        'deletion_access': bool(request.user.is_authenticated and request.user.is_active and age_access_allowed(request.user)),
    }, status=400 if error else 200)
    response['Cache-Control'] = 'no-store'
    return response

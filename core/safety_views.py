from django import forms
from django.db import DatabaseError, transaction
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods
from rest_framework.exceptions import APIException

from accounts.legal import TERMS_VERSION
from accounts.models import ContentReport
from accounts.security import enforce_auth_limit
from .legal import legal_context


class SafetyContactForm(forms.Form):
    contact_email = forms.EmailField(required=False, max_length=254, label='Reply email (optional)')
    details = forms.CharField(min_length=10, max_length=2000, strip=True,
        widget=forms.Textarea(attrs={'rows': 7, 'maxlength': 2000}), label='Describe the child-safety concern')


@never_cache
@sensitive_post_parameters('details', 'contact_email')
@require_http_methods(['GET', 'HEAD', 'POST'])
def child_safety_report(request):
    status, retry = 200, None
    form = SafetyContactForm()
    if request.method == 'POST':
        try:
            enforce_auth_limit(request, 'safety_report')
        except APIException as exc:
            status, retry = exc.status_code, getattr(exc, 'wait', None)
            form = SafetyContactForm({})
            form.is_valid()
            form.add_error(None, 'Reporting is temporarily unavailable. Please retry or use the configured safety/support contact.')
        else:
            form = SafetyContactForm(request.POST)
            if request.FILES:
                form.add_error(None, 'Text only. Do not upload suspected CSAM or identity documents.')
            if form.is_valid():
                # No account, target lookup, attachment or email delivery is required.
                try:
                    with transaction.atomic():
                        ContentReport.objects.create(reporter=None, target_type='safety', target_id=0,
                            reason='child_safety', **form.cleaned_data)
                except DatabaseError:
                    form.add_error(None, 'Your report could not be stored. Please retry or use the configured safety/support contact.')
                    status = 503
                else:
                    request.session['safety_report_received'] = True
                    return redirect('child_safety_report')
            else:
                status = 400
    received = request.session.pop('safety_report_received', False) if request.method == 'GET' else False
    response = render(request, 'core/public_page.html', {**legal_context(), 'page': 'child-safety-report',
        'terms_version': TERMS_VERSION, 'form': form, 'received': received}, status=status)
    if retry:
        response['Retry-After'] = str(int(retry))
    return response

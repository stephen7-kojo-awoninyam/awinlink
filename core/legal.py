"""Public operator details; configuration alone never approves draft policies."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from accounts.legal import POLICY_REVIEW_DATE


def legal_context():
    details = {
        'operator': settings.AWINLINK_LEGAL_OPERATOR,
        'legal_address': settings.AWINLINK_LEGAL_ADDRESS,
        'support_email': settings.AWINLINK_SUPPORT_EMAIL,
        'privacy_email': settings.AWINLINK_PRIVACY_EMAIL,
        'child_safety_email': settings.AWINLINK_CHILD_SAFETY_EMAIL,
    }
    for key in ('support_email', 'privacy_email', 'child_safety_email'):
        try:
            validate_email(details[key])
        except ValidationError:
            details[key] = ''
    return {**details, 'operator_details_complete': all(details.values()),
            'policy_review_date': POLICY_REVIEW_DATE}

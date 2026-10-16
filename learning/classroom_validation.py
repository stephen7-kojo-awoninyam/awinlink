"""Transport-independent validation for persisted classroom text."""
from django.core.exceptions import ValidationError


def validate_plaintext(value, *, nonblank=True, maximum=2000):
    if not isinstance(value, str) or not 1 <= len(value) <= maximum or (nonblank and not value.strip()):
        raise ValidationError("Text must contain 1–2000 characters.")
    if any(ord(char) < 32 and char not in "\n\t" for char in value):
        raise ValidationError("Text contains unsupported control characters.")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise ValidationError("Text must contain valid Unicode characters.")
    return value

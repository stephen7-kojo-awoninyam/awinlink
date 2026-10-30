"""Bounded validation for instructor supplied lesson caption tracks."""
import re

from django.core.exceptions import ValidationError


MAX_CAPTION_BYTES = 2 * 1024 * 1024
MAX_CAPTION_CUES = 10_000
_TIMESTAMP = re.compile(r'(?:(?P<hours>\d{2,}):)?(?P<minutes>[0-5]?\d):(?P<seconds>[0-5]\d)\.(?P<millis>\d{3})')
_TIMING = re.compile(r'^(?P<start>(?:(?:\d{2,}):)?[0-5]?\d:[0-5]\d\.\d{3})\s+-->\s+(?P<end>(?:(?:\d{2,}):)?[0-5]?\d:[0-5]\d\.\d{3})(?:\s+[^\r\n]*)?$')
_SAFE_TAG = re.compile(r'</?(?:b|i|u|c(?:\.[a-zA-Z0-9_-]+)?|v(?:\s+[^<>]{1,80})?|lang\s+[a-zA-Z0-9-]{2,35})>', re.I)


def _seconds(value):
    match = _TIMESTAMP.fullmatch(value)
    if not match:
        raise ValueError
    return (int(match.group('hours') or 0) * 3600 + int(match.group('minutes')) * 60
            + int(match.group('seconds')) + int(match.group('millis')) / 1000)


def validate_webvtt(upload):
    """Accept UTF-8 WebVTT cues only; reject mislabeled or malformed uploads."""
    name = getattr(upload, 'name', '') or ''
    size = getattr(upload, 'size', None)
    if not name.lower().endswith('.vtt') or not isinstance(size, int) or size <= 0 or size > MAX_CAPTION_BYTES:
        raise ValidationError('Choose a non-empty .vtt caption file no larger than 2 MB.')
    try:
        position = upload.tell()
        upload.seek(0)
        raw = upload.read(MAX_CAPTION_BYTES + 1)
    except (AttributeError, OSError, ValueError):
        raise ValidationError('The caption file could not be read.') from None
    finally:
        try:
            upload.seek(position)
        except (AttributeError, OSError, ValueError, UnboundLocalError):
            pass
    if len(raw) > MAX_CAPTION_BYTES:
        raise ValidationError('Caption files must be no larger than 2 MB.')
    try:
        text = raw.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n')
    except UnicodeDecodeError:
        raise ValidationError('Caption files must use UTF-8 text.') from None
    if '\x00' in text or '\ufffd' in text:
        raise ValidationError('The caption file contains invalid text.')
    lines = text.split('\n')
    if not lines or not re.fullmatch(r'WEBVTT(?:[ \t].*)?', lines[0]) or len(lines) < 3 or lines[1].strip():
        raise ValidationError('The caption file must start with a valid WEBVTT header and a blank line.')
    body = '\n'.join(lines[2:])
    blocks = [block for block in re.split(r'\n[ \t]*\n', body) if block.strip()]
    count = 0
    for block in blocks:
        cue = block.split('\n')
        if cue[0].startswith(('NOTE', 'STYLE', 'REGION')):
            if cue[0].startswith('NOTE'):
                continue
            raise ValidationError('Caption STYLE and REGION blocks are not supported.')
        timing_index = 0 if '-->' in cue[0] else 1
        if timing_index >= len(cue):
            raise ValidationError('A caption cue is missing its time range.')
        timing = _TIMING.fullmatch(cue[timing_index])
        if not timing:
            raise ValidationError('Caption cues must use valid WebVTT timestamps.')
        try:
            if _seconds(timing['end']) <= _seconds(timing['start']):
                raise ValueError
        except ValueError:
            raise ValidationError('Each caption cue must end after it starts.') from None
        lines_of_text = cue[timing_index + 1:]
        cue_text = '\n'.join(lines_of_text)
        if not cue_text.strip() or len(cue_text) > 5000:
            raise ValidationError('Each caption cue must contain readable text under 5,000 characters.')
        tags = re.findall(r'<[^>]*>', cue_text)
        if any(not _SAFE_TAG.fullmatch(tag) for tag in tags) or re.search(r'<[^>]*$', cue_text):
            raise ValidationError('Caption cues contain unsupported markup.')
        count += 1
        if count > MAX_CAPTION_CUES:
            raise ValidationError('Caption files may contain no more than 10,000 cues.')
    if count == 0:
        raise ValidationError('Add at least one timed caption cue.')


def validate_transcript(value):
    if len(value or '') > 100_000:
        raise ValidationError('Transcripts must be 100,000 characters or fewer.')

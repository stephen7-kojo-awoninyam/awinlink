"""Bounded upload checks and inert delivery for untrusted file bytes.

Container signatures are a type check, not malware scanning. Documents are always
downloads; only a small raster/audio/video MIME allowlist can render inline.
"""
import codecs
import os

from django.conf import settings
from django.core.exceptions import BadRequest, ValidationError
from django.utils.http import content_disposition_header


IMAGE_TYPES = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'jfif': 'image/jpeg',
    'png': 'image/png', 'gif': 'image/gif', 'webp': 'image/webp', 'bmp': 'image/bmp',
    'tif': 'image/tiff', 'tiff': 'image/tiff', 'avif': 'image/avif',
    'heic': 'image/heic', 'heif': 'image/heif'}
VIDEO_TYPES = {'mp4': 'video/mp4', 'm4v': 'video/mp4', 'mov': 'video/quicktime',
    'webm': 'video/webm', 'mkv': 'video/x-matroska', 'avi': 'video/x-msvideo',
    '3gp': 'video/3gpp', '3g2': 'video/3gpp2', 'mpeg': 'video/mpeg', 'mpg': 'video/mpeg', 'ts': 'video/mp2t'}
AUDIO_TYPES = {'mp3': 'audio/mpeg', 'm4a': 'audio/mp4', 'mp4': 'audio/mp4',
    'aac': 'audio/aac', 'webm': 'audio/webm', 'ogg': 'audio/ogg', 'oga': 'audio/ogg',
    'opus': 'audio/ogg', 'wav': 'audio/wav', 'flac': 'audio/flac', 'amr': 'audio/amr'}
DOCUMENT_EXTENSIONS = frozenset({'pdf', 'txt', 'csv', 'md', 'json', 'rtf', 'doc', 'docx',
    'xls', 'xlsx', 'ppt', 'pptx', 'odt', 'ods', 'odp', 'zip', 'gz', 'tar', '7z', 'rar'})
INLINE_TYPES = frozenset([*IMAGE_TYPES.values(), *VIDEO_TYPES.values(), *AUDIO_TYPES.values()])
HEAD_BYTES = 4096
ERROR = 'Unsupported or invalid file. Use a supported image, recording, video or document within the upload limit.'


class UnsafeUpload(BadRequest):
    pass


class UnsafeStoredUpload(ValidationError):
    pass


def extension(name):
    return os.path.splitext(str(name).replace('\\', '/').rsplit('/', 1)[-1])[1].lstrip('.').lower()


def field_kind(field):
    if field in {'image', 'thumbnail', 'logo', 'profile_photo', 'profile_picture', 'cover_photo'}:
        return 'image'
    if field == 'captions':
        return 'captions'
    return field if field in {'audio', 'video'} else 'file'


def path_kind(path):
    if path.startswith('learning/captions/'):
        return 'captions'
    if path.startswith(('messages/audio/',)):
        return 'audio'
    if path.startswith(('feed/videos/', 'messages/videos/', 'learning/videos/')):
        return 'video'
    if path.startswith(('feed/images/', 'messages/images/', 'messages/groups/', 'profiles/',
        'talents/profile/', 'talents/cover/', 'organizations/logos/', 'organizations/covers/',
        'athletes/profile/', 'athletes/cover/', 'coaches/profiles/', 'coaches/covers/',
        'learning/thumbnails/', 'portfolio/images/', 'achievements/', 'events/images/', 'sports/icons/')):
        return 'image'
    if path.startswith(('events/gallery/', 'athletes/media/')):
        return 'media'
    return 'file'


def allowed_extensions(kind):
    return {'image': set(IMAGE_TYPES), 'audio': set(AUDIO_TYPES), 'video': set(VIDEO_TYPES),
        'media': set(IMAGE_TYPES) | set(VIDEO_TYPES), 'captions': {'vtt'}}.get(kind,
            set(IMAGE_TYPES) | set(AUDIO_TYPES) | set(VIDEO_TYPES) | DOCUMENT_EXTENSIONS | {'vtt'})


def size_limit(kind):
    defaults = {'image': 20, 'audio': 50, 'video': 200, 'media': 200, 'file': 25, 'captions': 2}
    return int(getattr(settings, 'AWINLINK_UPLOAD_LIMITS', {}).get(kind, defaults[kind] * 1024 * 1024))


def valid_signature(ext, head):
    if ext in {'jpg', 'jpeg', 'jfif'}:
        return head.startswith(b'\xff\xd8\xff')
    if ext == 'png':
        return head.startswith(b'\x89PNG\r\n\x1a\n')
    if ext == 'gif':
        return head.startswith((b'GIF87a', b'GIF89a'))
    if ext in {'webp', 'wav', 'avi'}:
        return head.startswith(b'RIFF') and head[8:12] == {'webp': b'WEBP', 'wav': b'WAVE', 'avi': b'AVI '}[ext]
    if ext == 'bmp':
        return head.startswith(b'BM')
    if ext in {'tif', 'tiff'}:
        return head.startswith((b'II*\x00', b'MM\x00*'))
    if ext in {'mp4', 'm4v', 'mov', 'm4a', '3gp', '3g2', 'avif', 'heic', 'heif'}:
        if len(head) < 12 or head[4:8] != b'ftyp':
            # Older QuickTime files may start with a moov or mdat atom.
            return ext == 'mov' and head[4:8] in {b'moov', b'mdat', b'wide'}
        brands = {head[i:i+4] for i in [8, *range(16, min(len(head), 64), 4)]}
        image_brands = {b'avif', b'avis', b'heic', b'heix', b'hevc', b'hevx', b'mif1', b'msf1'}
        if ext in {'avif', 'heic', 'heif'}:
            return bool(brands & ({b'avif', b'avis'} if ext == 'avif' else image_brands - {b'avif', b'avis'}))
        return not bool(brands & image_brands)
    if ext in {'webm', 'mkv'}:
        return head.startswith(b'\x1aE\xdf\xa3')
    if ext in {'ogg', 'oga', 'opus'}:
        return head.startswith(b'OggS')
    if ext in {'mp3', 'aac'}:
        return (ext == 'mp3' and head.startswith(b'ID3')) or (len(head) >= 2 and head[0] == 255 and head[1] & 0xe0 == 0xe0)
    if ext == 'amr':
        return head.startswith((b'#!AMR\n', b'#!AMR-WB\n'))
    if ext == 'flac':
        return head.startswith(b'fLaC')
    if ext in {'mpeg', 'mpg'}:
        return head.startswith((b'\x00\x00\x01\xba', b'\x00\x00\x01\xb3'))
    if ext == 'ts':
        return len(head) > 188 and head[0] == head[188] == 0x47
    if ext == 'pdf':
        return head.startswith(b'%PDF-')
    if ext in {'docx', 'xlsx', 'pptx', 'odt', 'ods', 'odp', 'zip'}:
        return head.startswith((b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08'))
    if ext in {'doc', 'xls', 'ppt'}:
        return head.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1')
    if ext == 'rtf':
        return head.startswith(b'{\\rtf')
    if ext == 'gz':
        return head.startswith(b'\x1f\x8b')
    if ext == '7z':
        return head.startswith(b'7z\xbc\xaf\x27\x1c')
    if ext == 'rar':
        return head.startswith(b'Rar!\x1a\x07')
    if ext == 'tar':
        return head[257:262] == b'ustar'
    if ext in {'txt', 'csv', 'md', 'json', 'vtt'}:
        try:
            codecs.getincrementaldecoder('utf-8')().decode(head, final=False)
        except UnicodeDecodeError:
            return False
        return b'\x00' not in head and (ext != 'vtt' or head.lstrip(b'\xef\xbb\xbf').startswith(b'WEBVTT'))
    return False


def validate_header(name, head, size, kind='file'):
    ext = extension(name)
    if size <= 0 or size > size_limit(kind) or ext not in allowed_extensions(kind) or not valid_signature(ext, head):
        raise UnsafeUpload(ERROR)


def validate_stored_upload(name, content):
    """Check new storage writes without changing any existing file or stream position."""
    position = content.tell()
    try:
        content.seek(0, 2)
        size = content.tell()
        content.seek(0)
        kind, ext = path_kind(name), extension(name)
        if kind == 'file':
            kind = 'image' if ext in IMAGE_TYPES else 'video' if ext in VIDEO_TYPES else 'audio' if ext in AUDIO_TYPES else 'file'
        validate_header(name, content.read(HEAD_BYTES), size, kind)
    except UnsafeUpload as error:
        raise UnsafeStoredUpload(ERROR) from error
    finally:
        content.seek(position)


def apply_media_headers(response, path, *, remote_type=None, playback=None):
    kind, ext = path_kind(path), extension(path)
    media = {**IMAGE_TYPES, **VIDEO_TYPES} if kind == 'media' else {
        'image': IMAGE_TYPES, 'video': VIDEO_TYPES, 'audio': AUDIO_TYPES}.get(kind, {})
    content_type = media.get(ext)
    if remote_type is not None:
        declared = remote_type.split(';', 1)[0].strip().lower()
        # Cloud public IDs may lack extensions. Only safe types for the owning
        # namespace qualify; HTML/SVG/XML and upstream disposition never pass.
        content_type = declared if declared in media.values() else None
    if playback and kind in {'audio', 'video', 'media'} and (remote_type is None or content_type):
        content_type = 'audio/mpeg' if playback == 'mp3' else 'video/mp4'
    if path.startswith('learning/captions/') and ext == 'vtt':
        content_type = 'text/vtt; charset=utf-8'
    response['Content-Type'] = content_type or 'application/octet-stream'
    filename = path.replace('\\', '/').rsplit('/', 1)[-1]
    filename = ''.join(c for c in filename if ord(c) >= 32 and ord(c) != 127)[:200] or 'download'
    response['Content-Disposition'] = content_disposition_header(not bool(content_type), filename)
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Security-Policy'] = "sandbox; default-src 'none'; base-uri 'none'; form-action 'none'"
    response['Referrer-Policy'] = 'no-referrer'
    response['Cache-Control'] = 'private, no-store'
    return response

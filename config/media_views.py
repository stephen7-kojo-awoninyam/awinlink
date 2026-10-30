"""Permission checked streaming for private local and Cloudinary media."""
import re
import subprocess

import requests
from cloudinary.utils import cloudinary_url
from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.storage import FileSystemStorage, default_storage
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse, StreamingHttpResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from django.views.decorators.cache import never_cache

from .media_storage import PlaybackMediaStorage
from .upload_security import apply_media_headers, path_kind
from .resource_limits import ResourceLimited, ResourceUnavailable


def _stored_names(path):
    names = {path}
    prefix = settings.CLOUDINARY_STORAGE.get("PREFIX", "media").strip("/")
    if prefix:
        names.add(f"{prefix}/{path}")
    return names


def _media_is_allowed(user, path):
    """Resolve the database object by storage name and apply its normal ACL."""
    if ('\\' in path or len(path) > 1024 or any(
        part in {'', '.', '..', '.playback-cache'} for part in path.split('/'))):
        return False
    names = _stored_names(path)
    if path.startswith(('talents/profile/', 'talents/cover/', 'achievements/', 'certifications/')):
        from talents.visibility import visible_talent_profiles_for
        return visible_talent_profiles_for(user).filter(
            Q(profile_photo__in=names) | Q(cover_photo__in=names) |
            Q(achievements__image__in=names) | Q(certifications__certificate_file__in=names)).exists()
    if path.startswith(('athletes/profile/', 'athletes/cover/', 'athletes/media/')):
        from athletes.visibility import visible_athlete_profiles_for
        return visible_athlete_profiles_for(user).filter(
            Q(profile_photo__in=names) | Q(cover_photo__in=names) | Q(media__file__in=names)).exists()
    if path.startswith(('events/images/', 'events/gallery/')):
        from events.visibility import visible_events_for
        return visible_events_for(user).filter(Q(image__in=names) | Q(media__file__in=names)).exists()
    if path.startswith(('portfolio/images/', 'portfolio/files/')):
        from portfolio.permissions import visible_portfolio_items_for
        return visible_portfolio_items_for(user).filter(Q(image__in=names) | Q(file__in=names)).exists()
    if path.startswith("feed/images/") or path.startswith("feed/videos/"):
        from feed.api_views import PostDetailAPIView
        from feed.models import Post
        post = Post.objects.filter(Q(image__in=names) | Q(video__in=names)).first()
        return bool(post and PostDetailAPIView().can_view_post(user, post))

    if path.startswith("messages/"):
        from messaging.models import Conversation, Message
        if not user.is_authenticated:
            return False
        if path.startswith("messages/groups/"):
            return Conversation.objects.filter(
                image__in=names, participants__user=user,
            ).exists()
        return Message.objects.filter(
            Q(image__in=names) | Q(video__in=names) | Q(audio__in=names) | Q(file__in=names),
            conversation__participants__user=user,
        ).exists()

    if path.startswith(("learning/videos/", "learning/notes/", "learning/captions/")):
        from learning.models import Enrollment, Lesson
        lesson = Lesson.objects.filter(Q(video__in=names) | Q(notes__in=names) | Q(captions__in=names)).select_related('course').first()
        return bool(lesson and user.is_authenticated and (
            lesson.course.creator_id == user.pk or user.role == 'ADMIN' or
            Enrollment.objects.filter(user=user, course_id=lesson.course_id).exists()))
    if path.startswith('verification_documents/'):
        from talents.verification_permissions import can_read_verification_document
        return can_read_verification_document(user, names)
    if path.startswith('certificates/'):
        from learning.models import Certificate
        return user.is_authenticated and Certificate.objects.filter(pdf__in=names, enrollment__user=user).exists()
    # Existing public media namespaces retain their public behavior, but never
    # bypass MIME/disposition/CSP protection through Django's raw static view.
    return path.startswith(('profiles/',
        'organizations/logos/', 'organizations/covers/', 'coaches/profiles/', 'coaches/covers/',
        'learning/thumbnails/',
        'sports/icons/'))


def _cloud_url(storage, path, resource_type, media_format, *, authenticated):
    public_id = storage._prepend_prefix(path)
    options = {
        "resource_type": resource_type,
        "type": "authenticated" if authenticated else "upload",
        "secure": True,
    }
    if resource_type == "video" and media_format:
        options["format"] = media_format
        if media_format == "mp4":
            options.update(video_codec="h264", audio_codec="aac")
        elif media_format == "mp3":
            options["audio_codec"] = "mp3"
    if authenticated:
        options["sign_url"] = True
    return cloudinary_url(public_id, **options)[0]


def _cloud_response(request, path, media_format):
    storage = default_storage
    path_name = storage._media_name(path)
    # Range offsets and Content-Length refer to original bytes, not a compressed
    # transfer representation that requests would transparently decompress.
    headers = {'Accept-Encoding': 'identity'}
    if request.headers.get("Range"):
        headers["Range"] = request.headers["Range"]

    session = requests.Session()
    session.trust_env = False
    try:
        resources = storage.resource_candidates(path)
        remote = None
        for resource in resources:
            for authenticated in ((True, False) if path_name.startswith(storage.PRIVATE_PREFIXES) else (False, True)):
                remote = session.get(
                    _cloud_url(storage, path_name, resource, media_format, authenticated=authenticated),
                    headers=headers, stream=True, allow_redirects=True, timeout=(3, 10),
                )
                if remote.status_code != 404:
                    break
                remote.close()
            if remote.status_code != 404:
                break
        if remote.status_code == 404:
            remote.close()
            session.close()
            raise Http404
        if remote.status_code not in (200, 206):
            remote.close()
            session.close()
            return HttpResponse("Media delivery is temporarily unavailable.", status=502)
        encoded = remote.headers.get('Content-Encoding', '').lower() not in {'', 'identity'}
        if encoded and remote.status_code == 206:
            remote.close()
            session.close()
            return HttpResponse('Unable to deliver a compressed byte range.', status=502)
        content_type = remote.headers.get("Content-Type", "application/octet-stream")
        if request.method == "HEAD":
            status_code = remote.status_code
            length = remote.headers.get("Content-Length")
            content_range = remote.headers.get("Content-Range")
            accepts_ranges = remote.headers.get("Accept-Ranges")
            remote.close()
            session.close()
            response = HttpResponse(status=status_code, content_type=content_type)
            if length and length.isdigit() and not encoded:
                response["Content-Length"] = length
            if content_range:
                response["Content-Range"] = content_range
            if accepts_ranges:
                response["Accept-Ranges"] = accepts_ranges
            return response

        def chunks():
            try:
                for chunk in remote.iter_content(chunk_size=65536):
                    if chunk:
                        yield chunk
            finally:
                remote.close()
                session.close()
        response = StreamingHttpResponse(chunks(), status=remote.status_code, content_type=content_type)
        for header in ("Content-Length", "Content-Range", "Accept-Ranges"):
            value = remote.headers.get(header)
            if value and (header != "Content-Length" or (value.isdigit() and not encoded)):
                response[header] = value
        return response
    except Http404:
        raise
    except (requests.RequestException, OSError, ValueError):
        session.close()
        return HttpResponse("Media delivery is temporarily unavailable.", status=502)


@never_cache
@api_view(["GET", "HEAD"])
@permission_classes([AllowAny])
def playback_media(request, path):
    if not _media_is_allowed(request.user, path):
        raise Http404

    storage = default_storage
    media_format = request.query_params.get("playback")
    if media_format:
        expected = "mp3" if path.startswith("messages/audio/") else "mp4"
        if media_format != expected or path_kind(path) not in {'audio', 'video', 'media'}:
            return HttpResponse("Unsupported playback format.", status=400)

    if isinstance(storage, PlaybackMediaStorage) and not FileSystemStorage(location=settings.MEDIA_ROOT).exists(path):
        response = _cloud_response(request, path, media_format)
        return apply_media_headers(response, path, remote_type=response.get('Content-Type'), playback=media_format)

    local_storage = FileSystemStorage(location=settings.MEDIA_ROOT)
    try:
        if media_format:
            expected = "mp3" if path.startswith("messages/audio/") else "mp4"
            from .media_transcoding import playback_copy
            derivative = playback_copy(local_storage.path(path), expected)
            media = local_storage.open(str(derivative), "rb")
        else:
            media = local_storage.open(path, "rb")
    except (ResourceLimited, ResourceUnavailable) as exc:
        response = HttpResponse(str(exc.detail), status=exc.status_code)
        if getattr(exc, 'wait', None):
            response['Retry-After'] = str(exc.wait)
        return response
    except (subprocess.SubprocessError, RuntimeError):
        return HttpResponse("Unable to prepare this media for playback. The original is unchanged.", status=422)
    except (OSError, SuspiciousFileOperation):
        raise Http404

    size = media.size
    content_type = 'application/octet-stream'
    start, end = 0, size - 1
    range_header = request.headers.get("Range")
    if range_header:
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header) if len(range_header) < 128 else None
        if not match or not any(match.groups()):
            media.close()
            return HttpResponse(status=416, headers={"Content-Range": f"bytes */{size}"})
        first, last = match.groups()
        if first:
            start = int(first)
            end = min(int(last), end) if last else end
        else:
            start = max(0, size - int(last))
        if start > end or start >= size:
            media.close()
            return HttpResponse(status=416, headers={"Content-Range": f"bytes */{size}"})
    length = end - start + 1
    if request.method == "HEAD":
        media.close()
        response = HttpResponse(content_type=content_type, status=206 if range_header else 200)
    elif range_header:
        media.seek(start)
        def chunks():
            remaining = length
            try:
                while remaining:
                    chunk = media.read(min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk
            finally:
                media.close()
        response = StreamingHttpResponse(chunks(), status=206, content_type=content_type)
    else:
        response = FileResponse(media, content_type=content_type)
    response["Accept-Ranges"] = "bytes"
    response["Content-Length"] = str(length)
    if range_header:
        response["Content-Range"] = f"bytes {start}-{end}/{size}"
    return apply_media_headers(response, path, playback=media_format)

"""Permission checked streaming for private local and Cloudinary media."""
import mimetypes
import os
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

from .media_storage import PlaybackMediaStorage


def _stored_names(path):
    names = {path}
    prefix = settings.CLOUDINARY_STORAGE.get("PREFIX", "media").strip("/")
    if prefix:
        names.add(f"{prefix}/{path}")
    return names


def _media_is_allowed(user, path):
    """Resolve the database object by storage name and apply its normal ACL."""
    names = _stored_names(path)
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

    if path.startswith(("learning/videos/", "learning/notes/")):
        from learning.models import Enrollment, Lesson
        lesson = Lesson.objects.filter(Q(video__in=names) | Q(notes__in=names)).values("course_id").first()
        return bool(lesson and user.is_authenticated and Enrollment.objects.filter(
            user=user, course_id=lesson["course_id"],
        ).exists())
    return False


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
    resource_type = storage._get_resource_type(path)
    headers = {}
    if request.headers.get("Range"):
        headers["Range"] = request.headers["Range"]

    session = requests.Session()
    session.trust_env = False
    try:
        remote = session.get(
            _cloud_url(storage, path_name, resource_type, media_format, authenticated=True),
            headers=headers, stream=True, allow_redirects=True, timeout=(3, 10),
        )
        # Previously uploaded Cloudinary files are public `upload` assets.
        # Keep them working through this ACL-protected proxy during migration.
        if remote.status_code == 404:
            remote.close()
            remote = session.get(
                _cloud_url(storage, path_name, resource_type, media_format, authenticated=False),
                headers=headers, stream=True, allow_redirects=True, timeout=(3, 10),
            )
        if remote.status_code == 404:
            remote.close()
            session.close()
            raise Http404
        if remote.status_code not in (200, 206):
            remote.close()
            session.close()
            return HttpResponse("Media delivery is temporarily unavailable.", status=502)
        content_type = remote.headers.get("Content-Type", "application/octet-stream")
        if media_format == "mp3":
            content_type = "audio/mpeg"
        elif media_format == "mp4":
            content_type = "video/mp4"
        if request.method == "HEAD":
            status_code = remote.status_code
            length = remote.headers.get("Content-Length")
            content_range = remote.headers.get("Content-Range")
            accepts_ranges = remote.headers.get("Accept-Ranges")
            remote.close()
            session.close()
            response = HttpResponse(status=status_code, content_type=content_type)
            if length and length.isdigit():
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
            if value and (header != "Content-Length" or value.isdigit()):
                response[header] = value
        return response
    except Http404:
        raise
    except (requests.RequestException, OSError, ValueError):
        session.close()
        return HttpResponse("Media delivery is temporarily unavailable.", status=502)


@api_view(["GET", "HEAD"])
@permission_classes([AllowAny])
def playback_media(request, path):
    if not _media_is_allowed(request.user, path):
        raise Http404

    storage = default_storage
    media_format = request.query_params.get("playback")
    if media_format:
        expected = "mp3" if path.startswith("messages/audio/") else "mp4"
        if media_format != expected:
            return HttpResponse("Unsupported playback format.", status=400)

    if isinstance(storage, PlaybackMediaStorage) and not FileSystemStorage(location=settings.MEDIA_ROOT).exists(path):
        response = _cloud_response(request, path, media_format)
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        if path.startswith(("messages/files/", "learning/notes/")):
            filename = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(path)) or "download"
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    local_storage = FileSystemStorage(location=settings.MEDIA_ROOT)
    try:
        if media_format:
            expected = "mp3" if path.startswith("messages/audio/") else "mp4"
            from .media_transcoding import playback_copy
            derivative = playback_copy(local_storage.path(path), expected)
            media = local_storage.open(str(derivative), "rb")
        else:
            media = local_storage.open(path, "rb")
    except (subprocess.SubprocessError, RuntimeError):
        return HttpResponse("Unable to prepare this media for playback. The original is unchanged.", status=422)
    except (OSError, SuspiciousFileOperation):
        raise Http404

    size = media.size
    content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    if path.startswith("messages/audio/") and not media_format:
        content_type = {".webm": "audio/webm", ".ogg": "audio/ogg", ".oga": "audio/ogg",
                        ".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4"}.get(
                            os.path.splitext(path)[1].lower(), "application/octet-stream")
    elif path.startswith("messages/files/") or path.startswith("learning/notes/"):
        content_type = "application/octet-stream"
    elif media_format == "mp3":
        content_type = "audio/mpeg"
    elif media_format == "mp4":
        content_type = "video/mp4"
    start, end = 0, size - 1
    range_header = request.headers.get("Range")
    if range_header:
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
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
    if path.startswith(("messages/files/", "learning/notes/")):
        filename = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(path)) or "download"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response

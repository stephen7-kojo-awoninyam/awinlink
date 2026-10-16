"""Permission checked, seekable delivery for existing local AV files."""
import mimetypes
import re
import subprocess

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.storage import FileSystemStorage
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse, StreamingHttpResponse
from rest_framework.decorators import api_view


@api_view(['GET', 'HEAD'])
def playback_media(request, path):
    from feed.api_views import PostDetailAPIView
    from feed.models import Post
    from messaging.models import Message

    if path.startswith('feed/videos/'):
        post = Post.objects.filter(video=path).first()
        allowed = post and PostDetailAPIView().can_view_post(request.user, post)
    else:
        allowed = Message.objects.filter(
            Q(audio=path) | Q(video=path),
            conversation__participants__user=request.user,
        ).exists()
    if not allowed:
        raise Http404
    storage = FileSystemStorage(location=settings.MEDIA_ROOT)
    try:
        media_format = request.query_params.get('playback')
        if media_format:
            expected = 'mp3' if path.startswith('messages/audio/') else 'mp4'
            if media_format != expected:
                return HttpResponse('Unsupported playback format.', status=400)
            from .media_transcoding import playback_copy
            derivative = playback_copy(storage.path(path), media_format)
            media = storage.open(str(derivative), 'rb')
        else:
            media = storage.open(path, 'rb')
    except (subprocess.SubprocessError, RuntimeError):
        return HttpResponse('Unable to prepare this media for playback. The original is unchanged.', status=422)
    except (OSError, SuspiciousFileOperation):
        raise Http404
    size = media.size
    content_type = mimetypes.guess_type(path)[0] or 'application/octet-stream'
    if media_format:
        content_type = 'audio/mpeg' if media_format == 'mp3' else 'video/mp4'
    elif path.startswith('messages/audio/'):
        extension = path.rsplit('.', 1)[-1].lower()
        content_type = {'webm': 'audio/webm', 'mp4': 'audio/mp4', 'm4a': 'audio/mp4',
                        'ogg': 'audio/ogg', 'mp3': 'audio/mpeg', 'wav': 'audio/wav'}.get(extension, content_type)
    start, end = 0, size - 1
    range_header = request.headers.get('Range')
    if range_header:
        match = re.fullmatch(r'bytes=(\d*)-(\d*)', range_header)
        if not match or not any(match.groups()):
            media.close()
            return HttpResponse(status=416, headers={'Content-Range': f'bytes */{size}'})
        first, last = match.groups()
        if first:
            start = int(first)
            end = min(int(last), end) if last else end
        else:
            start = max(0, size - int(last))
        if start > end or start >= size:
            media.close()
            return HttpResponse(status=416, headers={'Content-Range': f'bytes */{size}'})
    length = end - start + 1
    if request.method == 'HEAD':
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
        response._resource_closers.append(media.close)
    else:
        response = FileResponse(media, content_type=content_type)
    response['Accept-Ranges'] = 'bytes'
    response['Content-Length'] = str(length)
    response['Cache-Control'] = 'private, no-store'
    if range_header:
        response['Content-Range'] = f'bytes {start}-{end}/{size}'
    return response

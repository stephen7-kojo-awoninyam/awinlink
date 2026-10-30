"""Create disposable playback derivatives; never rewrite an uploaded original."""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile

from django.conf import settings
from imageio_ffmpeg import get_ffmpeg_exe
from .resource_limits import Lease


def playback_copy(source, media_format):
    source = Path(source)
    stat = source.stat()
    key = hashlib.sha256(f'v1:{source}:{stat.st_mtime_ns}:{stat.st_size}:{media_format}'.encode()).hexdigest()
    cache = Path(settings.MEDIA_ROOT) / '.playback-cache'
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / f'{key}.{media_format}'
    if target.exists():
        return target
    # Acquire the source lock first, so duplicate viewers never consume every
    # worker slot waiting for the same derivative. Busy callers retry later.
    source_lease = Lease('transcoding_file', key).acquire()
    global_lease = None
    try:
        if target.exists():
            return target
        global_lease = Lease('transcoding', 'cluster').acquire()
        return _produce(source, media_format, cache, target)
    finally:
        from contextlib import suppress
        from .resource_limits import ResourceUnavailable
        with suppress(ResourceUnavailable):
            source_lease.release()
        if global_lease is not None:
            with suppress(ResourceUnavailable):
                global_lease.release()


def _produce(source, media_format, cache, target):
    descriptor, temporary = tempfile.mkstemp(suffix=f'.{media_format}', dir=cache)
    os.close(descriptor)
    try:
        command = [get_ffmpeg_exe(), '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                   '-protocol_whitelist', 'file,pipe',
                   '-format_whitelist', 'mov,mp4,m4a,3gp,3g2,mj2,matroska,webm,ogg,wav,mp3,avi,flv,mpeg,mpegts',
                   '-i', str(source), '-map_metadata', '-1', '-threads', '1']
        if media_format == 'mp3':
            command += ['-vn', '-c:a', 'libmp3lame', '-b:a', '128k']
        else:
            command += ['-map', '0:v:0', '-map', '0:a:0?', '-c:v', 'libx264', '-preset', 'fast',
                        '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p',
                        '-c:a', 'aac', '-movflags', '+faststart']
        # Malformed media can produce enormous diagnostics. Neither output
        # stream is needed for delivery; never buffer it in worker memory.
        subprocess.run([*command, temporary], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        os.replace(temporary, target)
        return target
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

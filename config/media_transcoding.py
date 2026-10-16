"""Create disposable playback derivatives; never rewrite an uploaded original."""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile

from django.conf import settings
from imageio_ffmpeg import get_ffmpeg_exe


def playback_copy(source, media_format):
    source = Path(source)
    stat = source.stat()
    key = hashlib.sha256(f'v1:{source}:{stat.st_mtime_ns}:{stat.st_size}:{media_format}'.encode()).hexdigest()
    cache = Path(settings.MEDIA_ROOT) / '.playback-cache'
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / f'{key}.{media_format}'
    if target.exists():
        return target
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
        subprocess.run([*command, temporary], check=True, capture_output=True, timeout=60,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        os.replace(temporary, target)
        return target
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

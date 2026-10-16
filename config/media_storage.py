"""Route AV assets to Cloudinary's video API without changing stored names."""
from cloudinary.utils import cloudinary_url
from cloudinary_storage.storage import MediaCloudinaryStorage
from django.core.files.storage import FileSystemStorage


class LocalPlaybackStorage(FileSystemStorage):
    def url(self, name):
        url = super().url(name)
        if name.startswith('messages/audio/'):
            return url + '?playback=mp3'
        if name.startswith(('feed/videos/', 'messages/videos/')):
            return url + '?playback=mp4'
        return url


class PlaybackMediaStorage(MediaCloudinaryStorage):
    # Use upload folders, since Cloudinary public IDs normally have no extension.
    AUDIO_PREFIX = "messages/audio/"
    VIDEO_PREFIXES = ("feed/videos/", "messages/videos/")

    def _media_name(self, name):
        name = self._normalise_name(name)
        prefix = self._get_prefix().strip('/')
        if prefix and name.startswith(prefix + '/'):
            name = name[len(prefix) + 1:]
        return name

    def _get_resource_type(self, name):
        name = self._media_name(name)
        if name.startswith((self.AUDIO_PREFIX, *self.VIDEO_PREFIXES)):
            return "video"
        return super()._get_resource_type(name)

    def _get_url(self, name):
        local = LocalPlaybackStorage()
        # Retain existing on-disk media when cloud storage is enabled later.
        if local.exists(name):
            return local.url(name)
        if self._get_resource_type(name) != "video":
            return super()._get_url(name)
        audio = self._media_name(name).startswith(self.AUDIO_PREFIX)
        options = {"resource_type": "video", "secure": True,
                   "format": "mp3" if audio else "mp4"}
        if not audio:
            options.update(video_codec="h264", audio_codec="aac")
        return cloudinary_url(self._prepend_prefix(name), **options)[0]

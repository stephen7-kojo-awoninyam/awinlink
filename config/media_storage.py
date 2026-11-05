"""Route AV assets to Cloudinary's video API without changing stored names."""
from cloudinary_storage.storage import MediaCloudinaryStorage
from django.core.files.storage import FileSystemStorage
from django.core.files import File
import requests
import tempfile
import os
from django.core.exceptions import SuspiciousFileOperation
from .upload_security import extension, path_kind, validate_stored_upload


class MediaDeletionConflict(Exception):
    """A provider asset cannot be safely identified for physical erasure."""


class LocalPlaybackStorage(FileSystemStorage):
    def _save(self, name, content):
        validate_stored_upload(name, content)
        return super()._save(name, content)

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
    PRIVATE_PREFIXES = (
        "profiles/", "coaches/profiles/", "coaches/covers/",
        "feed/images/", "feed/videos/", "messages/groups/", "messages/images/",
        "messages/videos/", "messages/audio/", "messages/files/",
        "learning/videos/", "learning/notes/", "learning/captions/",
        "verification_documents/", "certificates/",
        "portfolio/images/", "portfolio/files/",
        "events/images/", "events/gallery/",
        "athletes/profile/", "athletes/cover/", "athletes/media/",
        "talents/profile/", "talents/cover/", "achievements/", "certifications/",
    )

    def _media_name(self, name):
        name = self._normalise_name(name)
        prefix = self._get_prefix().strip('/')
        if prefix and name.startswith(prefix + '/'):
            name = name[len(prefix) + 1:]
        return name

    def resource_candidates(self, name):
        kind = self._get_resource_type(name)
        return [kind, 'image'] if kind == 'raw' else [kind, 'video'] if path_kind(self._media_name(name)) == 'media' and kind == 'image' else [kind]

    def _fetch_cloud(self, name, *, method='get'):
        # Storage reads/metadata must use signed provider URLs, never the public
        # app URL returned by url(). The caller owns response/session cleanup.
        from .media_views import _cloud_url
        session = requests.Session()
        session.trust_env = False
        private = self._media_name(name).startswith(self.PRIVATE_PREFIXES)
        try:
            for resource in self.resource_candidates(name):
                for authenticated in ((True, False) if private else (False, True)):
                    response = getattr(session, method)(_cloud_url(self, self._media_name(name), resource, None,
                        authenticated=authenticated), headers={'Accept-Encoding': 'identity'}, timeout=(3, 10), stream=True)
                    if response.status_code != 404:
                        return session, response
                    response.close()
            return session, response
        except Exception:
            session.close()
            raise

    def _open(self, name, mode='rb'):
        if mode != 'rb':
            raise ValueError('Cloud media can only be opened for binary reading.')
        session, response = self._fetch_cloud(name)
        temporary = tempfile.SpooledTemporaryFile(max_size=2 * 1024 * 1024)
        try:
            response.raise_for_status()
            for chunk in response.iter_content(chunk_size=65536):
                temporary.write(chunk)
            temporary.seek(0)
            return File(temporary, name=name)
        except Exception:
            temporary.close()
            raise
        finally:
            response.close()
            session.close()

    def exists(self, name):
        session, response = self._fetch_cloud(name, method='head')
        try:
            if response.status_code == 404:
                return False
            response.raise_for_status()
            return True
        finally:
            response.close()
            session.close()

    def size(self, name):
        session, response = self._fetch_cloud(name, method='head')
        try:
            response.raise_for_status()
            return int(response.headers['Content-Length'])
        finally:
            response.close()
            session.close()

    def _get_resource_type(self, name):
        name = self._media_name(name)
        if name.startswith((self.AUDIO_PREFIX, *self.VIDEO_PREFIXES)):
            return "video"
        kind = path_kind(name)
        if kind == 'video' or (kind == 'media' and extension(name) in {'mp4', 'mov', 'm4v', 'webm', 'mkv', 'avi', '3gp', '3g2', 'mpeg', 'mpg', 'ts'}):
            return 'video'
        if kind in {'file', 'captions'}:
            return 'raw'
        return super()._get_resource_type(name)

    def _upload(self, name, content):
        media_name = self._media_name(name)
        validate_stored_upload(media_name, content)
        options = {"use_filename": True, "resource_type": self._get_resource_type(name), "tags": self.TAG}
        if options['resource_type'] == 'raw':
            options['flags'] = 'attachment'
        folder = os.path.dirname(name)
        if folder:
            options["folder"] = folder
        if media_name.startswith(self.PRIVATE_PREFIXES):
            # Private uploads start private; no public delivery window is created.
            options["type"] = "authenticated"
            if media_name.startswith(self.AUDIO_PREFIX):
                options["eager"] = [{"format": "mp3", "audio_codec": "mp3"}]
            elif media_name.startswith(self.VIDEO_PREFIXES):
                options["eager"] = [{"format": "mp4", "video_codec": "h264", "audio_codec": "aac"}]
        from cloudinary import uploader
        return uploader.upload(content, **options)

    def delete(self, name):
        # django-cloudinary-storage calls destroy(type='upload') implicitly.
        # That misses authenticated assets and can target a different legacy
        # delivery type with the same public ID. Destructive callers must supply
        # a retention-approved, immutable asset ID and exact delivery identity.
        raise MediaDeletionConflict('Cloudinary deletion requires an audited asset identity.')

    def delete_asset(self, name, *, asset_id, resource_type, delivery_type):
        """Delete one verified Cloudinary identity after policy checks by caller.

        This deliberately does not choose a retention rule or decide ownership.
        Callers must first check holds/shared references and persist the deletion
        request. Public-ID-only legacy cleanup is rejected as ambiguous.
        """
        if (not isinstance(asset_id, str) or not asset_id or len(asset_id) > 256
                or resource_type not in self.resource_candidates(name)
                or delivery_type not in {'upload', 'private', 'authenticated'}):
            raise MediaDeletionConflict('Cloudinary deletion identity is incomplete.')
        media_name = self._media_name(name)
        if ('\\' in media_name or any(part in {'', '.', '..'} for part in media_name.split('/'))):
            raise SuspiciousFileOperation('Invalid Cloudinary media name.')
        public_id = self._prepend_prefix(media_name)
        from cloudinary import api, uploader
        from cloudinary.exceptions import NotFound
        try:
            current = api.resource(public_id, resource_type=resource_type, type=delivery_type)
        except NotFound:
            return False
        if current.get('asset_id') != asset_id:
            raise MediaDeletionConflict('Cloudinary asset identity changed; deletion was cancelled.')
        result = uploader.destroy(public_id, resource_type=resource_type,
            type=delivery_type, invalidate=True)
        if result.get('result') == 'not found':
            return False
        if result.get('result') != 'ok':
            raise MediaDeletionConflict('Cloudinary did not confirm asset deletion.')
        return True

    def _get_url(self, name):
        media_name = self._media_name(name)
        # Every application URL uses the same delivery headers, including public
        # profiles and old active-content files. Stored names remain unchanged.
        return LocalPlaybackStorage().url(media_name)

    def url(self, name):
        if self._media_name(name).startswith(self.PRIVATE_PREFIXES):
            return self._get_url(name)
        return super().url(name)

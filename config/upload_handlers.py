"""Validate multipart uploads for both Django forms and DRF before persistence."""
from django.conf import settings
from django.core.files.uploadhandler import FileUploadHandler
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
import time
from rest_framework.exceptions import APIException

from .resource_limits import Lease, ResourceUnavailable, consume
from .http_limits import body_limit, check_length

from .upload_security import (AUDIO_TYPES, IMAGE_TYPES, VIDEO_TYPES, ERROR, HEAD_BYTES,
    UnsafeStoredUpload, UnsafeUpload, extension, field_kind, size_limit, validate_header)


class SecureUploadHandler(FileUploadHandler):
    def __init__(self, request=None):
        super().__init__(request)
        self.total = 0

    def new_file(self, field_name, file_name, *args, **kwargs):
        super().new_file(field_name, file_name, *args, **kwargs)
        if not hasattr(self, 'resource_lease'):
            # This handler runs before CSRF/DRF parsing. Resolve identity without
            # reading request.data and without trusting submitted owner/org IDs.
            from accounts.authentication import RevocableJWTAuthentication
            from accounts.recovery import client_address
            from django.contrib.auth import get_user
            identity = RevocableJWTAuthentication().authenticate(self.request)
            user = identity[0] if identity else get_user(self.request)
            self.resource_identity = ('user:' + str(user.pk) if user.is_authenticated
                                      else 'anonymous:' + client_address(self.request))
            self.resource_budget = 'upload_bytes' if user.is_authenticated else 'anonymous_upload_bytes'
            self.resource_lease = Lease('upload_connections', self.resource_identity).acquire()
            self.global_lease = getattr(self.request, 'scope', {}).get('_awinlink_upload_global_lease')
            self.owns_global_lease = self.global_lease is None
            if self.owns_global_lease:
                self.global_lease = Lease('upload_global', 'cluster').acquire()
            self.renew_at = time.monotonic() + min(self.resource_lease.ttl, self.global_lease.ttl) / 3
        self.kind = field_kind(field_name)
        if self.kind == 'file':
            ext = extension(file_name)
            self.kind = ('image' if ext in IMAGE_TYPES else 'video' if ext in VIDEO_TYPES
                         else 'audio' if ext in AUDIO_TYPES else 'file')
        self.head = bytearray()

    def receive_data_chunk(self, raw_data, start):
        self.total += len(raw_data)
        if (start + len(raw_data) > size_limit(self.kind) or
            self.total > int(getattr(settings, 'AWINLINK_UPLOAD_TOTAL_BYTES', 250 * 1024 * 1024))):
            raise UnsafeUpload(ERROR)
        if time.monotonic() >= self.renew_at:
            self.resource_lease.renew()
            self.global_lease.renew()
            self.renew_at = time.monotonic() + min(self.resource_lease.ttl, self.global_lease.ttl) / 3
        # Charge attempted work, including later rejected/abandoned uploads.
        # Failed requests cannot reset their allowance by repeatedly aborting.
        if raw_data:
            consume(self.resource_budget, self.resource_identity, len(raw_data))
        self.head.extend(raw_data[:max(0, HEAD_BYTES - len(self.head))])
        return raw_data

    def file_complete(self, file_size):
        validate_header(self.file_name, bytes(self.head), file_size, self.kind)
        return None


class UploadSecurityMiddleware(MiddlewareMixin):
    def process_request(self, request):
        # WSGI does not have Django's pre-view ASGI spool. Reject oversized JSON
        # here before DRF reads it; ASGI additionally counts actual body chunks.
        if request.content_type == 'application/json' or request.content_type.endswith('+json'):
            try:
                _, limit = body_limit(request.content_type)
                check_length(request.META.get('CONTENT_LENGTH'), limit)
            except APIException as exc:
                return self.resource_error(request, exc)
        # Parse before CSRF for POST, so parser failures have the same controlled
        # JSON error as DRF's lazy multipart PUT/PATCH parsing. Valid CSRF rules
        # are still enforced by the next middleware.
        if request.method == 'POST' and request.content_type == 'multipart/form-data':
            try:
                request.FILES
            except UnsafeUpload:
                return self.invalid(request)
            except APIException as exc:
                return self.resource_error(request, exc)

    def process_exception(self, request, exception):
        if isinstance(exception, (UnsafeUpload, UnsafeStoredUpload)):
            return self.invalid(request)
        if isinstance(exception, APIException):
            return self.resource_error(request, exception)

    def process_response(self, request, response):
        for handler in request.upload_handlers:
            for lease in (getattr(handler, 'resource_lease', None),
                          getattr(handler, 'global_lease', None) if getattr(handler, 'owns_global_lease', True) else None):
                if lease is None:
                    continue
                try:
                    lease.release()
                except ResourceUnavailable:
                    pass  # The abandoned lease expires; no unprotected retry.
        return response

    @staticmethod
    def resource_error(request, exception):
        for handler in request.upload_handlers:
            file = getattr(handler, 'file', None)
            if file is not None:
                file.close()
        response = JsonResponse({'detail': str(exception.detail)}, status=exception.status_code)
        if getattr(exception, 'wait', None):
            response['Retry-After'] = str(exception.wait)
        response['Cache-Control'] = 'private, no-store'
        return response

    @staticmethod
    def invalid(request):
        field = 'file'
        for handler in request.upload_handlers:
            if isinstance(handler, SecureUploadHandler):
                field = getattr(handler, 'field_name', 'file')
            file = getattr(handler, 'file', None)
            if file is not None:
                file.close()
        if field not in {'image', 'video', 'audio', 'file', 'thumbnail', 'logo', 'profile_photo',
            'profile_picture', 'cover_photo', 'document', 'certificate_file', 'artifact', 'notes'}:
            field = 'file'
        response = JsonResponse({'detail': ERROR, 'errors': {field: [ERROR]}}, status=400)
        response['Cache-Control'] = 'no-store'
        return response

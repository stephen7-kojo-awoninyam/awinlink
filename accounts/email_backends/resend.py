"""Django email over Resend HTTPS. Never logs credentials, bodies or provider replies."""
import base64
from email.utils import getaddresses
import json
import re
import ssl
from urllib.error import HTTPError
from urllib.request import HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import uuid4

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.validators import validate_email
from django.views.decorators.debug import sensitive_variables

ENDPOINT = 'https://api.resend.com/emails'


class ResendDeliveryError(Exception):
    """A deliberately redacted delivery failure."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def api_key_valid(value):
    return isinstance(value, str) and bool(re.fullmatch(r're_[A-Za-z0-9_-]+', value))


def mailbox(value):
    if not isinstance(value, str) or '\r' in value or '\n' in value:
        raise ValueError
    parsed = getaddresses([value])
    if len(parsed) != 1:
        raise ValueError
    validate_email(parsed[0][1])
    return parsed[0][1]


@sensitive_variables()
def payload_for(message):
    mailbox(message.from_email)
    if not isinstance(message.subject, str) or '\r' in message.subject or '\n' in message.subject:
        raise ValueError
    payload = {'from': message.from_email, 'to': [mailbox(value) for value in message.to],
               'subject': message.subject}
    for field in ('cc', 'bcc', 'reply_to'):
        values = getattr(message, field, [])
        if values:
            payload[field] = [mailbox(value) for value in values]
    if message.content_subtype not in ('plain', 'html'):
        raise ValueError
    payload['html' if message.content_subtype == 'html' else 'text'] = message.body
    for content, mimetype in getattr(message, 'alternatives', []):
        if mimetype not in ('text/plain', 'text/html'):
            raise ValueError
        payload['html' if mimetype == 'text/html' else 'text'] = content
    if message.extra_headers:
        reserved = {'from', 'to', 'cc', 'bcc', 'reply-to', 'subject', 'content-type', 'mime-version', 'authorization', 'idempotency-key'}
        for name, value in message.extra_headers.items():
            if (not re.fullmatch(r'[A-Za-z0-9-]+', name) or name.lower() in reserved
                    or not isinstance(value, str) or '\r' in value or '\n' in value):
                raise ValueError
        payload['headers'] = dict(message.extra_headers)
    if message.attachments:
        attachments = []
        for attachment in message.attachments:
            if isinstance(attachment, tuple):
                filename, content, mimetype = attachment
            else:
                filename, content, mimetype = attachment.get_filename(), attachment.get_payload(decode=True), attachment.get_content_type()
            if isinstance(content, str):
                content = content.encode(message.encoding or settings.DEFAULT_CHARSET)
            attachments.append({'filename': filename or 'attachment',
                                'content': base64.b64encode(content).decode('ascii')})
        payload['attachments'] = attachments
    return payload


class EmailBackend(BaseEmailBackend):
    @sensitive_variables()
    def send_messages(self, email_messages):
        sent = 0
        for message in email_messages or []:
            if not message.recipients():
                continue
            try:
                self._send(message)
                sent += 1
            except Exception:
                if not self.fail_silently:
                    raise ResendDeliveryError('Email provider delivery failed; details withheld.') from None
        return sent

    @sensitive_variables()
    def _send(self, message):
        key = getattr(settings, 'RESEND_API_KEY', '')
        timeout = getattr(settings, 'RESEND_TIMEOUT', 10)
        if not api_key_valid(key) or not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 60:
            raise ResendDeliveryError('Resend configuration is invalid; values withheld.')
        payload = payload_for(message)
        # Reusing this message object keeps its idempotency key. No automatic
        # retry: a network timeout can follow successful provider acceptance.
        if not getattr(message, '_resend_idempotency_key', None):
            message._resend_idempotency_key = 'awinlink-email/' + uuid4().hex
        request = Request(ENDPOINT, data=json.dumps(payload).encode('utf-8'), method='POST',
            headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json',
                     'User-Agent': 'Awinlink-Django-Mail', 'Idempotency-Key': message._resend_idempotency_key})
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        # Ignore ambient HTTP proxies; do not redirect bearer credentials/body.
        opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context), NoRedirect())
        try:
            with opener.open(request, timeout=timeout) as response:
                if response.status not in (200, 201, 202):
                    raise ResendDeliveryError('Email provider rejected the request.')
                raw = response.read(65537)
                if len(raw) > 65536:
                    raise ResendDeliveryError('Email provider response refused.')
                result = json.loads(raw)
                if not isinstance(result, dict) or not isinstance(result.get('id'), str) or not result['id']:
                    raise ResendDeliveryError('Email provider acceptance was not confirmed.')
        except HTTPError as error:
            error.close()
            raise ResendDeliveryError('Email provider rejected the request.') from None

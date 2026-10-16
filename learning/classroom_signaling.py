"""Validated peer messages and fenced, database-backed socket presence."""

import json
import ipaddress
import hashlib
import re
import time
from datetime import timedelta
from importlib import import_module

from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Exists, F, OuterRef, Q
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from . import classroom_services as services
from .classroom_events import emit_classroom_control
from .models import AdmissionState, AttendanceInterval, ClassroomRole, Enrollment


MAX_FRAME_BYTES = 65536
MAX_SDP_BYTES = 32768
MAX_CANDIDATE_BYTES = 4096


class SignalingDenied(Exception):
    def __init__(self, reason):
        self.reason = reason


def heartbeat_seconds():
    return max(0.05, float(getattr(settings, "CLASSROOM_WS_HEARTBEAT_SECONDS", 5)))


def lease_seconds():
    return max(3 * heartbeat_seconds(), float(getattr(settings, "CLASSROOM_WS_LEASE_SECONDS", 30)))


def public_generation(channel_name):
    # A reconnect version, not an authorization credential or channel address.
    return hashlib.sha256(channel_name.encode("utf-8")).hexdigest()[:32]


def credential_valid(user_id, *, claims=None, session_key=None):
    """Re-read canonical JWT or session authentication, including user revocation."""
    if claims is not None:
        try:
            if float(claims["exp"]) <= time.time():
                return False
            return JWTAuthentication().get_user(claims).pk == user_id
        except (AuthenticationFailed, InvalidToken, TokenError, KeyError, ValueError, TypeError):
            return False
    if not session_key:
        return False
    store = import_module(settings.SESSION_ENGINE).SessionStore(session_key=session_key)
    if str(store.get(SESSION_KEY, "")) != str(user_id) or store.get(BACKEND_SESSION_KEY) not in settings.AUTHENTICATION_BACKENDS:
        return False
    user = get_user_model().objects.filter(pk=user_id, is_active=True).first()
    if user is None:
        return False
    stored_hash = store.get(HASH_SESSION_KEY, "")
    hashes = [user.get_session_auth_hash(), *user.get_session_auth_fallback_hash()]
    return bool(stored_hash) and any(constant_time_compare(stored_hash, value) for value in hashes)


def connection_state(session_id, user_id, connection_id, channel_name, *, require_heartbeat=True):
    interval = AttendanceInterval.objects.filter(connection_id=connection_id,
        participant__session_id=session_id, participant__membership__user_id=user_id).select_related(
            "participant__membership__user", "participant__session__classroom__course").first()
    if interval is None:
        return "replaced"
    participant, member, session = interval.participant, interval.participant.membership, interval.participant.session
    if session.status != "LIVE" or session.ended_at is not None:
        return "ended"
    if not session.classroom.is_active or not member.user.is_active or not member.is_active:
        return "removed"
    if participant.admission_state != AdmissionState.ADMITTED or participant.role != member.role:
        return "removed"
    if member.role == ClassroomRole.LEARNER and (session.classroom.course.status != "APPROVED" or
        not Enrollment.objects.filter(user_id=user_id, course_id=session.classroom.course_id).exists()):
        return "removed"
    if interval.left_at is not None or interval.signaling_channel_name != channel_name:
        return "replaced"
    if require_heartbeat and (interval.signaling_heartbeat_at is None or
        interval.signaling_heartbeat_at <= timezone.now() - timedelta(seconds=lease_seconds())):
        return "replaced"
    return "authorized"


def _live_intervals(session_id):
    return AttendanceInterval.objects.filter(
        participant__session_id=session_id, left_at__isnull=True,
        signaling_channel_name__isnull=False,
        signaling_heartbeat_at__gt=timezone.now() - timedelta(seconds=lease_seconds()),
        participant__session__status="LIVE", participant__session__ended_at__isnull=True,
        participant__session__classroom__is_active=True,
        participant__membership__is_active=True, participant__membership__user__is_active=True,
        participant__admission_state=AdmissionState.ADMITTED,
        participant__role=F("participant__membership__role"),
    ).annotate(enrolled=Exists(Enrollment.objects.filter(
        user_id=OuterRef("participant__membership__user_id"),
        course_id=OuterRef("participant__session__classroom__course_id")))).filter(
            Q(participant__role__in=[ClassroomRole.HOST, ClassroomRole.COHOST]) |
            Q(participant__role=ClassroomRole.LEARNER, enrolled=True,
              participant__session__classroom__course__status="APPROVED"))


@transaction.atomic
def prepare_connection(*, actor, session_id, connection_id, channel_name):
    _, session = services._locked_session(session_id)
    interval = services.join_session(actor=actor, session=session, connection_id=connection_id)
    interval.signaling_channel_name, interval.signaling_heartbeat_at = channel_name, None
    interval.save(update_fields=["signaling_channel_name", "signaling_heartbeat_at"])
    state = connection_state(session_id, actor.pk, connection_id, channel_name, require_heartbeat=False)
    if state != "authorized":
        raise SignalingDenied(state)
    emit_classroom_control(session_id)
    return {"participant_id": interval.participant_id, "role": interval.participant.role}


@transaction.atomic
def renew_connection(*, session_id, user_id, connection_id, channel_name, activate=False):
    services._locked_session(session_id)
    state = connection_state(session_id, user_id, connection_id, channel_name, require_heartbeat=not activate)
    if state != "authorized":
        raise SignalingDenied(state)
    interval = AttendanceInterval.objects.get(connection_id=connection_id, signaling_channel_name=channel_name)
    interval.signaling_heartbeat_at = timezone.now()
    interval.save(update_fields=["signaling_heartbeat_at"])
    if activate:
        emit_classroom_control(session_id)


@transaction.atomic
def disconnect_connection(*, session_id, user_id, connection_id, channel_name):
    try:
        _, session = services._locked_session(session_id)
    except ObjectDoesNotExist:
        return False
    interval = AttendanceInterval.objects.filter(connection_id=connection_id,
        signaling_channel_name=channel_name, left_at__isnull=True, participant__session=session,
        participant__membership__user_id=user_id).select_related("participant").first()
    if interval is None:
        return False
    actor = get_user_model().objects.filter(pk=user_id).first()
    services._close(actor, session, interval.participant, timezone.now(), reason="socket_disconnected")
    emit_classroom_control(session_id)
    return True


def peers(session_id, participant_id):
    return [{"participant_id": row["participant_id"], "user_id": row["participant__membership__user_id"],
             "role": row["participant__role"], "generation": public_generation(row["signaling_channel_name"])} for row in _live_intervals(session_id).exclude(
                 participant_id=participant_id).order_by("participant_id").values(
                     "participant_id", "participant__membership__user_id", "participant__role", "signaling_channel_name")]


def recipient_connection(session_id, participant_id):
    return _live_intervals(session_id).filter(participant_id=participant_id).values(
        "connection_id", "signaling_channel_name").first()


def relay_is_current(session_id, sender_id, sender_connection, sender_channel, recipient_id, recipient_connection, recipient_channel):
    candidates = _live_intervals(session_id)
    return candidates.filter(participant_id=sender_id, connection_id=sender_connection,
        signaling_channel_name=sender_channel).exists() and candidates.filter(
            participant_id=recipient_id, connection_id=recipient_connection,
            signaling_channel_name=recipient_channel).exists()


def _reject_constant(value):
    raise ValueError("Non-finite JSON is not supported.")


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON keys are not supported.")
        result[key] = value
    return result


def parse_message(text):
    data = json.loads(text, object_pairs_hook=_unique_keys, parse_constant=_reject_constant)
    if not isinstance(data, dict):
        raise ValueError("Messages must be JSON objects.")
    return validate_message(data)


def _bounded_string(value, maximum, *, allow_empty=False):
    if not isinstance(value, str) or (not value and not allow_empty) or len(value.encode("utf-8")) > maximum:
        raise ValueError("Invalid signaling string.")
    if any(ord(char) < 32 and char not in "\r\n" for char in value) or "\x7f" in value:
        raise ValueError("Signaling contains control characters.")
    return value


def validate_message(data):
    kind = data.get("type")
    if not isinstance(kind, str):
        raise ValueError("A signaling type is required.")
    if kind == "ping" and set(data) == {"type"}:
        return {"type": "ping"}
    if kind not in {"offer", "answer", "ice_candidate"}:
        raise ValueError("Unsupported signaling type.")
    recipient = data.get("recipient_id")
    if type(recipient) is not int or not 0 < recipient <= 9223372036854775807:
        raise ValueError("A participant recipient is required.")
    field = "candidate" if kind == "ice_candidate" else "description"
    if set(data) != {"type", "recipient_id", field}:
        raise ValueError("Only signaling fields are accepted.")
    if kind in {"offer", "answer"}:
        description = data[field]
        if not isinstance(description, dict) or set(description) != {"type", "sdp"} or description["type"] != kind:
            raise ValueError("The SDP description type must match the message.")
        sdp = _bounded_string(description["sdp"], MAX_SDP_BYTES)
        lines = sdp.replace("\r\n", "\n").split("\n")
        if lines[0] != "v=0" or not all(any(line.startswith(prefix) for line in lines) for prefix in ["o=", "s=", "t=", "m="]):
            raise ValueError("A WebRTC SDP description is required.")
        if any(line and (len(line) < 2 or line[1] != "=") for line in lines):
            raise ValueError("Malformed SDP line.")
    else:
        candidate = data[field]
        if candidate is not None:
            if not isinstance(candidate, dict) or "candidate" not in candidate or set(candidate) - {
                "candidate", "sdpMid", "sdpMLineIndex", "usernameFragment"}:
                raise ValueError("Invalid ICE candidate fields.")
            value = _bounded_string(candidate["candidate"], MAX_CANDIDATE_BYTES, allow_empty=True)
            if "\r" in value or "\n" in value:
                raise ValueError("ICE must be a single line.")
            mid, index = candidate.get("sdpMid"), candidate.get("sdpMLineIndex")
            if mid is not None and (not isinstance(mid, str) or not mid or len(mid) > 64 or any(ord(char) < 33 or ord(char) > 126 for char in mid)):
                raise ValueError("Invalid ICE media ID.")
            if index is not None and (type(index) is not int or not 0 <= index <= 65535):
                raise ValueError("Invalid ICE media index.")
            if "usernameFragment" in candidate:
                fragment = _bounded_string(candidate["usernameFragment"], 256)
                if any(ord(char) < 33 or ord(char) > 126 for char in fragment):
                    raise ValueError("Invalid ICE username fragment.")
            if value:
                parts = value.split()
                if len(parts) < 8 or not parts[0].startswith("candidate:") or len(parts[0]) <= 10 or parts[2].lower() not in {"udp", "tcp"} or parts[6] != "typ" or parts[7] not in {"host", "srflx", "prflx", "relay"}:
                    raise ValueError("Malformed ICE candidate.")
                if not value.isascii() or not re.fullmatch(r"[A-Za-z0-9+/]{1,32}", parts[0][10:]):
                    raise ValueError("Invalid ICE foundation.")
                if (len(parts) - 8) % 2:
                    raise ValueError("Invalid ICE extensions.")
                if parts[1] not in {"1", "2"} or not parts[3].isdigit() or len(parts[3]) > 10 or int(parts[3]) > 4294967295 or not parts[5].isdigit() or len(parts[5]) > 5 or not 1 <= int(parts[5]) <= 65535:
                    raise ValueError("Invalid ICE component, priority or port.")
                try:
                    ipaddress.ip_address(parts[4])
                except ValueError:
                    if len(parts[4]) > 253 or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", parts[4]):
                        raise ValueError("Invalid ICE address.")
                if mid is None and index is None:
                    raise ValueError("ICE requires a media ID or index.")
    return data

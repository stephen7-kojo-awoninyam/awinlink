"""Validation for client-originated call signaling messages."""

import ipaddress
import re


MAX_CALL_SDP_BYTES = 32768
MAX_CALL_CANDIDATE_BYTES = 4096
MAX_CALL_SDP_MID_LENGTH = 64


def _positive_user_id(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 0 < value <= 9223372036854775807 else None
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,19}", value):
        parsed = int(value)
        return parsed if 0 < parsed <= 9223372036854775807 else None
    return None


def _validate_description(kind, value):
    if not isinstance(value, dict) or set(value) != {"type", "sdp"} or value.get("type") != kind:
        raise ValueError("Invalid session description.")
    sdp = value.get("sdp")
    if not isinstance(sdp, str) or not sdp or len(sdp.encode("utf-8")) > MAX_CALL_SDP_BYTES:
        raise ValueError("Invalid session description size.")
    if "\r" in sdp.replace("\r\n", ""):
        raise ValueError("Malformed session description lines.")
    if any((ord(char) < 32 and char not in "\r\n\t") or ord(char) == 127 for char in sdp):
        raise ValueError("Session description contains control characters.")
    lines = sdp.replace("\r\n", "\n").split("\n")
    if lines[0] != "v=0" or not all(any(line.startswith(prefix) for line in lines) for prefix in ("o=", "s=", "t=", "m=")):
        raise ValueError("A WebRTC session description is required.")
    if any(line and (len(line) < 2 or line[1] != "=") for line in lines):
        raise ValueError("Malformed session description line.")
    return {"type": kind, "sdp": sdp}


def _validate_candidate(value):
    if value is None:
        return None
    if not isinstance(value, dict) or "candidate" not in value or set(value) - {
        "candidate", "sdpMid", "sdpMLineIndex", "usernameFragment"
    }:
        raise ValueError("Invalid ICE candidate fields.")
    candidate = value["candidate"]
    if not isinstance(candidate, str) or len(candidate.encode("utf-8")) > MAX_CALL_CANDIDATE_BYTES:
        raise ValueError("Invalid ICE candidate size.")
    if "\r" in candidate or "\n" in candidate or any(ord(char) < 32 or ord(char) == 127 for char in candidate):
        raise ValueError("Malformed ICE candidate line.")
    if candidate and not candidate.startswith("candidate:"):
        raise ValueError("Malformed ICE candidate.")
    if candidate:
        parts = candidate.split()
        if len(parts) < 8 or (len(parts) - 8) % 2:
            raise ValueError("Malformed ICE candidate attributes.")
        foundation = parts[0][10:] if parts[0].startswith("candidate:") else ""
        if not foundation or len(foundation) > 32 or not re.fullmatch(r"[A-Za-z0-9+/]+", foundation):
            raise ValueError("Invalid ICE candidate foundation.")
        if parts[1] not in {"1", "2"} or parts[2].lower() not in {"udp", "tcp"} or parts[6] != "typ" or parts[7] not in {"host", "srflx", "prflx", "relay"}:
            raise ValueError("Invalid ICE candidate protocol.")
        if not parts[3].isdigit() or len(parts[3]) > 10 or int(parts[3]) > 4294967295:
            raise ValueError("Invalid ICE candidate priority.")
        if not parts[5].isdigit() or len(parts[5]) > 5 or not 1 <= int(parts[5]) <= 65535:
            raise ValueError("Invalid ICE candidate port.")
        try:
            ipaddress.ip_address(parts[4])
        except ValueError:
            if len(parts[4]) > 253 or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", parts[4]):
                raise ValueError("Invalid ICE candidate address.")
    mid = value.get("sdpMid")
    if mid is not None and (not isinstance(mid, str) or not mid or len(mid) > MAX_CALL_SDP_MID_LENGTH or any(ord(char) < 33 or ord(char) > 126 for char in mid)):
        raise ValueError("Invalid ICE media ID.")
    index = value.get("sdpMLineIndex")
    if index is not None and (type(index) is not int or not 0 <= index <= 65535):
        raise ValueError("Invalid ICE media index.")
    fragment = value.get("usernameFragment")
    if fragment is not None and (not isinstance(fragment, str) or not fragment or len(fragment) > 256 or any(ord(char) < 33 or ord(char) > 126 for char in fragment)):
        raise ValueError("Invalid ICE username fragment.")
    return dict(value)


def validate_call_signal(data):
    """Return a canonical client signal or raise ValueError.

    Legacy `ice-candidate`, `target_id`, and offer/answer aliases are accepted
    because older shipped clients used them. Server-owned identity is added by
    the consumer after validation.
    """
    if not isinstance(data, dict) or not isinstance(data.get("type"), str):
        raise ValueError("A signaling type is required.")
    kind = "ice_candidate" if data["type"] == "ice-candidate" else data["type"]
    if kind not in {"ready", "offer", "answer", "ice_candidate"}:
        raise ValueError("Unsupported signaling type.")

    recipient_fields = [key for key in ("to_user_id", "target_id") if key in data]
    if not recipient_fields:
        raise ValueError("A call participant recipient is required.")
    recipient = _positive_user_id(data[recipient_fields[0]])
    if recipient is None or any(_positive_user_id(data[key]) != recipient for key in recipient_fields[1:]):
        raise ValueError("Invalid signaling recipient.")

    common = {"type", "to_user_id", "target_id", "sender_id"}
    if kind == "ready":
        if set(data) - common:
            raise ValueError("Unexpected ready message fields.")
        return {"type": kind, "to_user_id": recipient, "target_id": recipient}

    if kind in {"offer", "answer"}:
        aliases = {"description", kind}
        if set(data) - common - aliases or not any(key in data for key in aliases):
            raise ValueError("Unexpected session description fields.")
        descriptions = [data[key] for key in aliases if key in data]
        if any(description != descriptions[0] for description in descriptions[1:]):
            raise ValueError("Conflicting session descriptions.")
        result = _validate_description(kind, descriptions[0])
        return {"type": kind, "to_user_id": recipient, "target_id": recipient, "description": result}

    if set(data) - common - {"candidate"} or "candidate" not in data:
        raise ValueError("Unexpected ICE candidate fields.")
    return {"type": kind, "to_user_id": recipient, "target_id": recipient, "candidate": _validate_candidate(data["candidate"])}

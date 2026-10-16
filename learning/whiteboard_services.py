"""Authoritative, bounded whiteboard commands shared by HTTP and Channels."""
import copy
import json
import math
import re
from uuid import UUID

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .classroom_permissions import require_active_user
from .classroom_validation import validate_plaintext
from .classroom_services import _locked_session
from .models import AdmissionState, ClassroomRole, Enrollment, LiveSession, SessionParticipant, Whiteboard, WhiteboardOperation


class RevisionConflict(ValidationError):
    pass


def group(session_id):
    return f"learning.whiteboard.{session_id}"


def access(actor, session, *, edit=False, host=False):
    actor = require_active_user(actor)
    participant = SessionParticipant.objects.select_related("membership", "session__classroom__course").filter(
        session=session, membership__user=actor, membership__is_active=True,
        admission_state=AdmissionState.ADMITTED).first()
    if participant is None or participant.role != participant.membership.role:
        raise PermissionDenied("Current admission is required.")
    if not session.classroom.is_active or session.status not in {LiveSession.Status.LIVE, LiveSession.Status.ENDED}:
        raise PermissionDenied("Whiteboard is unavailable.")
    if participant.role == ClassroomRole.LEARNER and (
        session.classroom.course.status != "APPROVED" or not Enrollment.objects.filter(
            user=actor, course=session.classroom.course).exists()):
        raise PermissionDenied("Current enrollment is required.")
    is_host = participant.role == ClassroomRole.HOST
    if host and not is_host:
        raise PermissionDenied("Only the admitted host controls the board.")
    if edit and session.status != LiveSession.Status.LIVE:
        raise PermissionDenied("Ended whiteboards are read only.")
    return participant, is_host


def validate_object(value):
    if not isinstance(value, dict):
        raise ValidationError("Invalid object.")
    kind = value.get("kind")
    common = {"id", "kind", "color", "width"}
    fields = {"stroke": {"points"}, "text": {"x", "y", "text", "size"},
              "rectangle": {"x", "y", "w", "h"}, "ellipse": {"x", "y", "w", "h"},
              "line": {"x", "y", "w", "h"}}
    if not isinstance(kind, str) or kind not in fields or set(value) != common | fields[kind]:
        raise ValidationError("Invalid object fields.")
    try:
        if str(UUID(value["id"])) != value["id"]:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise ValidationError("Object ID must be a canonical UUID.")
    if not isinstance(value["color"], str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value["color"]):
        raise ValidationError("Use a hex color.")
    def number(v, lo=0, hi=1):
        if type(v) not in (int, float) or not lo <= v <= hi or not math.isfinite(v):
            raise ValidationError("Invalid coordinate or size.")
    number(value["width"], .0001, .1)
    if kind == "stroke":
        points = value["points"]
        if not isinstance(points, list) or not 2 <= len(points) <= 2048:
            raise ValidationError("Invalid stroke points.")
        for point in points:
            if not isinstance(point, list) or len(point) != 2:
                raise ValidationError("Invalid point.")
            for coordinate in point:
                number(coordinate)
    else:
        number(value["x"]); number(value["y"])
        if kind == "text":
            number(value["size"], .001, .2)
            text = value["text"]
            validate_plaintext(text, nonblank=False)
        else:
            minimum = -1 if kind == "line" else 0
            number(value["w"], minimum); number(value["h"], minimum)
            number(value["x"] + value["w"]); number(value["y"] + value["h"])
    return copy.deepcopy(value)


def validate_document(objects):
    if not isinstance(objects, dict) or len(objects) > 1000:
        raise ValidationError("Board object limit exceeded.")
    for key, value in objects.items():
        validate_object(value)
        if key != value["id"]:
            raise ValidationError("Object key mismatch.")
    try:
        size = len(json.dumps(objects, allow_nan=False).encode())
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ValidationError("Invalid document encoding.")
    if size > 2_000_000:
        raise ValidationError("Board size limit exceeded.")


def _publish(session_id):
    def send():
        import logging
        try:
            layer = get_channel_layer()
            if layer:
                async_to_sync(layer.group_send)(group(session_id), {"type": "whiteboard_changed"})
        except Exception:
            logging.getLogger(__name__).exception("Whiteboard broadcast failed; clients recover by snapshot")
    transaction.on_commit(send)


def _granted(board, participant):
    # Grants belong to this admission, never to a future re-admission of the same row.
    return bool(participant.admitted_at and board.editors.get(str(participant.pk)) == participant.admitted_at.isoformat())


@transaction.atomic
def snapshot(*, actor, session_id):
    _, session = _locked_session(session_id)
    participant, host = access(actor, session)
    board, _ = Whiteboard.objects.get_or_create(session=session)
    return {"session_id": session.pk, "revision": board.revision, "objects": board.objects_data,
            "editors": [p.pk for p in session.participants.filter(admission_state=AdmissionState.ADMITTED,
                membership__is_active=True, role=ClassroomRole.LEARNER) if _granted(board, p)],
            "can_edit": session.status == LiveSession.Status.LIVE and (
                participant.role in {ClassroomRole.HOST, ClassroomRole.COHOST} or _granted(board, participant)),
            "can_manage": host and session.status == LiveSession.Status.LIVE}


@transaction.atomic
def command(*, actor, session_id, data):
    if not isinstance(data, dict) or set(data) != {"operation_id", "base_revision", "action", "payload"}:
        raise ValidationError("Invalid command fields.")
    try:
        operation_id = UUID(data["operation_id"])
    except (ValueError, TypeError, AttributeError):
        raise ValidationError("Invalid operation ID.")
    if type(data["base_revision"]) is not int or data["base_revision"] < 0:
        raise ValidationError("Invalid revision.")
    try:
        size = len(json.dumps(data, allow_nan=False).encode())
    except (ValueError, TypeError, OverflowError, RecursionError, UnicodeError):
        raise ValidationError("Invalid JSON values.")
    if size > 65536:
        raise ValidationError("Command too large.")
    _, session = _locked_session(session_id)
    participant, host = access(actor, session, edit=True)
    board, _ = Whiteboard.objects.get_or_create(session=session)
    action, payload = data["action"], data["payload"]
    if not isinstance(payload, dict) or not isinstance(action, str) or action not in {"add", "erase", "undo", "clear", "permission"}:
        raise ValidationError("Invalid action.")
    if action in {"clear", "permission"}:
        access(actor, session, edit=True, host=True)
    elif participant.role not in {ClassroomRole.HOST, ClassroomRole.COHOST} and not _granted(board, participant):
        raise PermissionDenied("Editing has not been granted.")
    previous = WhiteboardOperation.objects.filter(board=board, operation_id=operation_id).first()
    if previous:
        if previous.actor_id != actor.pk or previous.command != data:
            raise PermissionDenied("Operation ID already used.")
        return {"operation_id": str(operation_id), "revision": previous.revision, "replayed": True}
    if board.revision != data["base_revision"]:
        raise RevisionConflict("Refresh the snapshot before retrying with a new operation ID.")
    inverse = {}
    if action == "add":
        obj = validate_object(payload)
        if obj["id"] in board.objects_data:
            raise ValidationError("Object already exists.")
        board.objects_data[obj["id"]] = obj
        inverse = {"delete": [obj["id"]]}
    elif action == "erase":
        ids = payload.get("ids")
        if set(payload) != {"ids"} or not isinstance(ids, list) or not 1 <= len(ids) <= 100 or any(not isinstance(i, str) for i in ids) or len(set(ids)) != len(ids):
            raise ValidationError("Invalid erase selection.")
        if any(i not in board.objects_data for i in ids):
            raise ValidationError("Unknown object.")
        inverse = {"restore": {i: board.objects_data.pop(i) for i in ids}}
    elif action == "clear":
        if payload:
            raise ValidationError("Clear takes no payload.")
        inverse = {"restore": copy.deepcopy(board.objects_data)}
        board.objects_data = {}
    elif action == "permission":
        if set(payload) != {"participant_id", "allowed"} or type(payload["participant_id"]) is not int or not 0 < payload["participant_id"] <= 9223372036854775807 or type(payload["allowed"]) is not bool:
            raise ValidationError("Invalid permission.")
        target = SessionParticipant.objects.filter(pk=payload["participant_id"], session=session,
            role=ClassroomRole.LEARNER, admission_state=AdmissionState.ADMITTED, membership__is_active=True).first()
        if target is None:
            raise PermissionDenied("An admitted learner in this session is required.")
        if payload["allowed"]:
            board.editors[str(target.pk)] = target.admitted_at.isoformat()
        else:
            board.editors.pop(str(target.pk), None)
    else:
        if payload:
            raise ValidationError("Undo takes no payload.")
        # Only undo your own immediately preceding drawing change. No overwrite of later edits.
        last = WhiteboardOperation.objects.filter(board=board, revision=board.revision,
            actor=actor, action__in=["add", "erase", "clear"]).first()
        if last is None:
            raise ValidationError("No safe change to undo.")
        for key in last.inverse.get("delete", []):
            board.objects_data.pop(key, None)
        board.objects_data.update(last.inverse.get("restore", {}))
    validate_document(board.objects_data)
    board.revision += 1
    board.save()
    WhiteboardOperation.objects.create(board=board, operation_id=operation_id, actor=actor,
        revision=board.revision, action=action, command=data, inverse=inverse)
    _publish(session.pk)
    return {"operation_id": str(operation_id), "revision": board.revision, "replayed": False}

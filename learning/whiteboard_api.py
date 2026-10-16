from rest_framework.response import Response
from rest_framework.parsers import JSONParser
from rest_framework.exceptions import ParseError
from rest_framework.throttling import UserRateThrottle
import json

from .classroom_api_views import ClassroomAPIView, ClassroomConflict
from .whiteboard_services import RevisionConflict, command, snapshot
from .classroom_signaling import _unique_keys, _reject_constant
from . import classroom_chat


class WhiteboardJSONParser(JSONParser):
    def parse(self, stream, media_type=None, parser_context=None):
        raw = stream.read(65537)
        if len(raw) > 65536:
            raise ParseError("Command too large.")
        try:
            return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_keys,
                              parse_constant=_reject_constant)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise ParseError("Invalid JSON command.")


class WhiteboardWriteThrottle(UserRateThrottle):
    scope = "learning_whiteboard_write"
    rate = "600/min"

    def allow_request(self, request, view):
        return request.method in {"GET", "HEAD", "OPTIONS"} or super().allow_request(request, view)


class WhiteboardAPIView(ClassroomAPIView):
    parser_classes = [WhiteboardJSONParser]
    throttle_classes = [WhiteboardWriteThrottle]
    def get(self, request, session_id):
        return Response(snapshot(actor=request.user, session_id=session_id))

    def post(self, request, session_id):
        try:
            result = command(actor=request.user, session_id=session_id, data=request.data)
        except RevisionConflict as exc:
            raise ClassroomConflict(str(exc))
        return Response(result)


class ClassroomChatAPIView(ClassroomAPIView):
    parser_classes = [WhiteboardJSONParser]
    throttle_classes = [WhiteboardWriteThrottle]

    def get(self, request, session_id):
        from rest_framework import serializers
        after = serializers.IntegerField(min_value=0, max_value=9223372036854775807).run_validation(
            request.query_params.get("after", 0))
        return Response(classroom_chat.history_page(actor=request.user, session_id=session_id, after=after))

    def post(self, request, session_id):
        return Response(classroom_chat.send(actor=request.user, session_id=session_id, data=request.data), status=201)

"""Authenticated adapters around the existing classroom services."""

import logging

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import Exists, OuterRef, Prefetch, Q
from django.db.models.functions import Lower
from django.shortcuts import get_object_or_404
from django.utils.cache import patch_cache_control
from rest_framework import serializers, status
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import JSONParser
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import UserRateThrottle

from . import classroom_services as services
from .classroom_permissions import (
    require_active_user, require_classroom_management, require_course_creator, require_session_staff,
)
from .classroom_serializers import (
    AttendanceConnectionSerializer, AttendanceSerializer, ClassroomCreateSerializer, ClassroomSerializer,
    ConnectionActionSerializer, EmptyActionSerializer, LiveSessionSerializer,
    SessionParticipantSerializer, SessionScheduleSerializer,
    ClassroomInvitationCreateSerializer, ClassroomInvitationSerializer, ClassroomStaffSerializer, ClassroomStaffInputSerializer,
    ClassroomUserSearchInputSerializer, ClassroomUserSearchSerializer,
)
from .models import AttendanceInterval, Classroom, ClassroomInvitation, ClassroomMembership, ClassroomRole, Course, Enrollment, Lesson, LiveSession, SessionParticipant


logger = logging.getLogger(__name__)


class ActiveClassroomAccount(BasePermission):
    def has_permission(self, request, view):
        require_active_user(request.user)
        return True


class ClassroomConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The classroom changed during this request. Refresh and try again."
    default_code = "conflict"


class ClassroomPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


def visible_classrooms(user):
    """Enrollment enables discovery; a revoked membership overrides discovery."""
    memberships = ClassroomMembership.objects.filter(classroom_id=OuterRef("pk"), user=user)
    return Classroom.objects.annotate(
        requester_staff=Exists(memberships.filter(is_active=True, role__in=[ClassroomRole.HOST, ClassroomRole.COHOST])),
        requester_blocked=Exists(memberships.filter(is_active=False)),
        requester_enrolled=Exists(Enrollment.objects.filter(course_id=OuterRef("course_id"), user=user)),
    ).filter(
        Q(course__creator=user) | Q(requester_staff=True) |
        Q(is_active=True, course__status="APPROVED", requester_enrolled=True, requester_blocked=False)
    )


class ClassroomAPIView(APIView):
    permission_classes = [IsAuthenticated, ActiveClassroomAccount]
    parser_classes = [JSONParser]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        patch_cache_control(response, private=True, no_store=True)
        return response

    def handle_exception(self, exc):
        if isinstance(exc, DjangoValidationError):
            exc = ValidationError(exc.message_dict if hasattr(exc, "message_dict") else {"non_field_errors": exc.messages})
        elif isinstance(exc, DjangoPermissionDenied):
            exc = PermissionDenied(str(exc))
        elif isinstance(exc, ObjectDoesNotExist):
            exc = NotFound()
        elif isinstance(exc, IntegrityError):
            exc = ClassroomConflict()
        try:
            response = super().handle_exception(exc)
        except Exception:
            # Preserve diagnostics in server logs without exposing exceptions or SQL.
            logger.exception("Classroom API request failed")
            response = Response({"detail": "Unable to complete the classroom request."}, status=500)
        codes = {400: "invalid_request", 401: "not_authenticated", 403: "permission_denied",
                 404: "not_found", 405: "method_not_allowed", 406: "not_acceptable", 409: "conflict",
                 415: "unsupported_media_type", 429: "throttled", 500: "server_error"}
        data = response.data
        detail = data.get("detail") if isinstance(data, dict) else None
        error = {"code": codes.get(response.status_code, "request_failed"), "detail": detail or "Invalid request."}
        if detail is None:
            error["fields"] = data
        response.data = {"error": error}
        return response

    def classroom(self, request, classroom_id):
        return get_object_or_404(visible_classrooms(request.user), pk=classroom_id)

    def session(self, request, session_id):
        return get_object_or_404(LiveSession.objects.filter(classroom__in=visible_classrooms(request.user)), pk=session_id)

    def input(self, request, serializer_class=EmptyActionSerializer):
        serializer = serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def session_response(self, request, session, *, response_status=200):
        return Response(LiveSessionSerializer(session, context={"request": request}).data, status=response_status)

    def page(self, request, queryset, serializer_class):
        paginator = ClassroomPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(serializer_class(page, many=True, context={"request": request}).data)


class ClassroomListCreateAPIView(ClassroomAPIView):
    def get(self, request):
        queryset = visible_classrooms(request.user).order_by("-created_at", "-pk")
        if "course" in request.query_params:
            field = serializers.IntegerField(min_value=1)
            queryset = queryset.filter(course_id=field.run_validation(request.query_params["course"]))
        return self.page(request, queryset, ClassroomSerializer)

    def post(self, request):
        data = self.input(request, ClassroomCreateSerializer)
        course = get_object_or_404(Course, pk=data.pop("course"))
        require_course_creator(request.user, course)
        host_id = data.pop("host", None)
        host = get_object_or_404(get_user_model(), pk=host_id) if host_id is not None else None
        classroom = services.create_classroom(actor=request.user, course=course, host=host, **data)
        return Response(ClassroomSerializer(classroom, context={"request": request}).data, status=status.HTTP_201_CREATED)


class ClassroomDetailAPIView(ClassroomAPIView):
    def get(self, request, classroom_id):
        return Response(ClassroomSerializer(self.classroom(request, classroom_id), context={"request": request}).data)


class ClassroomSessionListScheduleAPIView(ClassroomAPIView):
    def get(self, request, classroom_id):
        classroom = self.classroom(request, classroom_id)
        queryset = classroom.live_sessions.order_by("-created_at", "-pk").prefetch_related(Prefetch(
            "participants", queryset=SessionParticipant.objects.filter(membership__user=request.user).select_related("membership"),
            to_attr="requester_participants"))
        return self.page(request, queryset, LiveSessionSerializer)

    def post(self, request, classroom_id):
        classroom = self.classroom(request, classroom_id)
        require_classroom_management(request.user, classroom)
        data = self.input(request, SessionScheduleSerializer)
        lesson = get_object_or_404(Lesson, pk=data.pop("lesson"), course_id=classroom.course_id)
        session = services.schedule_session(actor=request.user, classroom=classroom, lesson=lesson, **data)
        return self.session_response(request, session, response_status=status.HTTP_201_CREATED)


class SessionDetailAPIView(ClassroomAPIView):
    def get(self, request, session_id):
        return self.session_response(request, self.session(request, session_id))


class SessionParticipantsAPIView(ClassroomAPIView):
    def get(self, request, session_id):
        session = self.session(request, session_id)
        require_session_staff(request.user, session, allow_cohost=True)
        return self.page(request, session.participants.select_related("membership__user").order_by("pk"), SessionParticipantSerializer)


class SessionRequestAdmissionAPIView(ClassroomAPIView):
    def post(self, request, session_id):
        session = self.session(request, session_id)
        self.input(request)
        participant = services.request_admission(actor=request.user, session=session)
        return Response(SessionParticipantSerializer(participant).data)


class SessionStartAPIView(ClassroomAPIView):
    def post(self, request, session_id):
        session = self.session(request, session_id)
        self.input(request)
        return self.session_response(request, services.start_session(actor=request.user, session=session))


class SessionJoinAPIView(ClassroomAPIView):
    def post(self, request, session_id):
        session = self.session(request, session_id)
        data = self.input(request, ConnectionActionSerializer)
        interval = services.join_session(actor=request.user, session=session, **data)
        return Response(AttendanceConnectionSerializer(interval).data)


class SessionLeaveAPIView(ClassroomAPIView):
    def post(self, request, session_id):
        # Cleanup remains possible after unenrollment, classroom deactivation or
        # admission revocation. Only the authenticated actor's session is visible.
        session = get_object_or_404(LiveSession.objects.filter(participants__membership__user=request.user).distinct(), pk=session_id)
        data = self.input(request, ConnectionActionSerializer)
        interval = services.leave_session(actor=request.user, session=session, **data)
        return Response(AttendanceConnectionSerializer(interval).data)


class SessionAdmitParticipantAPIView(ClassroomAPIView):
    def post(self, request, session_id, participant_id):
        session = self.session(request, session_id)
        require_session_staff(request.user, session, allow_cohost=True)
        self.input(request)
        participant = get_object_or_404(SessionParticipant, pk=participant_id, session=session)
        result = services.admit_participant(actor=request.user, session=session, participant=participant)
        return Response(SessionParticipantSerializer(result).data)


class SessionRemoveParticipantAPIView(ClassroomAPIView):
    def post(self, request, session_id, participant_id):
        session = self.session(request, session_id)
        require_session_staff(request.user, session, allow_cohost=True)
        self.input(request)
        participant = get_object_or_404(SessionParticipant, pk=participant_id, session=session)
        result = services.remove_participant(actor=request.user, session=session, participant=participant)
        return Response(SessionParticipantSerializer(result).data)


class SessionEndAPIView(ClassroomAPIView):
    def post(self, request, session_id):
        session = self.session(request, session_id)
        self.input(request)
        return self.session_response(request, services.end_session(actor=request.user, session=session))


class SessionCancelAPIView(ClassroomAPIView):
    def post(self, request, session_id):
        session = self.session(request, session_id)
        self.input(request)
        return self.session_response(request, services.cancel_session(actor=request.user, session=session))


class SessionAttendanceAPIView(ClassroomAPIView):
    def get(self, request, session_id):
        session = self.session(request, session_id)
        queryset = AttendanceInterval.objects.filter(participant__session=session)
        try:
            require_session_staff(request.user, session, allow_cohost=True)
        except DjangoPermissionDenied:
            queryset = queryset.filter(participant__membership__user=request.user)
        return self.page(request, queryset.select_related("participant__membership").order_by("joined_at", "pk"), AttendanceSerializer)


class ClassroomInvitationListCreateAPIView(ClassroomAPIView):
    def get(self, request, classroom_id):
        classroom = self.classroom(request, classroom_id)
        require_classroom_management(request.user, classroom)
        return self.page(request, classroom.invitations.select_related("classroom", "recipient").order_by("-created_at", "-pk"),
                         ClassroomInvitationSerializer)

    def post(self, request, classroom_id):
        classroom = self.classroom(request, classroom_id)
        require_classroom_management(request.user, classroom)
        data = self.input(request, ClassroomInvitationCreateSerializer)
        recipient = get_object_or_404(get_user_model(), pk=data.pop("recipient"))
        invitation, created = services.invite_classroom_user(actor=request.user, classroom=classroom, recipient=recipient, **data)
        return Response(ClassroomInvitationSerializer(invitation).data, status=201 if created else 200)


class MyClassroomInvitationsAPIView(ClassroomAPIView):
    def get(self, request):
        return self.page(request, ClassroomInvitation.objects.filter(recipient=request.user).select_related("classroom", "recipient").order_by("-created_at", "-pk"),
                         ClassroomInvitationSerializer)


class ClassroomInvitationDetailAPIView(ClassroomAPIView):
    def get(self, request, invitation_id):
        invitation = get_object_or_404(ClassroomInvitation.objects.select_related("classroom"),
                                       pk=invitation_id, recipient=request.user)
        return Response(ClassroomInvitationSerializer(invitation).data)


class ClassroomInvitationAcceptAPIView(ClassroomAPIView):
    def post(self, request, invitation_id):
        invitation = get_object_or_404(ClassroomInvitation, pk=invitation_id, recipient=request.user)
        self.input(request)
        result = services.accept_classroom_invitation(actor=request.user, invitation=invitation)
        return Response(ClassroomInvitationSerializer(result).data)


class ClassroomInvitationDeclineAPIView(ClassroomAPIView):
    def post(self, request, invitation_id):
        invitation = get_object_or_404(ClassroomInvitation, pk=invitation_id, recipient=request.user)
        self.input(request)
        result = services.decline_classroom_invitation(actor=request.user, invitation=invitation)
        return Response(ClassroomInvitationSerializer(result).data)


class ClassroomInvitationRevokeAPIView(ClassroomAPIView):
    def post(self, request, classroom_id, invitation_id):
        classroom = self.classroom(request, classroom_id)
        require_classroom_management(request.user, classroom)
        invitation = get_object_or_404(ClassroomInvitation, pk=invitation_id, classroom=classroom)
        self.input(request)
        result = services.revoke_classroom_invitation(actor=request.user, invitation=invitation)
        return Response(ClassroomInvitationSerializer(result).data)


class ClassroomStaffAPIView(ClassroomAPIView):
    def get(self, request, classroom_id):
        classroom = self.classroom(request, classroom_id)
        require_course_creator(request.user, classroom.course)
        return self.page(request, classroom.memberships.filter(is_active=True, role__in=[ClassroomRole.HOST, ClassroomRole.COHOST]).select_related("user").order_by("pk"), ClassroomStaffSerializer)

    def post(self, request, classroom_id):
        classroom = self.classroom(request, classroom_id)
        require_course_creator(request.user, classroom.course)
        data = self.input(request, ClassroomStaffInputSerializer)
        user = get_object_or_404(get_user_model(), pk=data["user"])
        if data["role"] == "REMOVE":
            services.remove_classroom_cohost(actor=request.user, classroom=classroom, user=user)
            return Response(status=204)
        if data["role"] == "COHOST" and classroom.memberships.filter(user=user, is_active=True, role=ClassroomRole.HOST).exists():
            raise ValidationError("Transfer the host role before changing the current host.")
        member = services.assign_classroom_role(actor=request.user, classroom=classroom, user=user, role=data["role"])
        return Response(ClassroomStaffSerializer(member).data)


class ClassroomUserSearchThrottle(UserRateThrottle):
    scope = "classroom_user_search"
    rate = "30/min"


class ClassroomUserSearchAPIView(ClassroomAPIView):
    throttle_classes = [ClassroomUserSearchThrottle]

    def get(self, request, classroom_id):
        classroom = self.classroom(request, classroom_id)
        # Authorize before validating or querying usernames. This is not a public directory.
        require_classroom_management(request.user, classroom)
        query = ClassroomUserSearchInputSerializer(data={
            "q": request.query_params.get("q", ""),
            "purpose": request.query_params.get("purpose", ""),
        })
        query.is_valid(raise_exception=True)
        purpose = query.validated_data["purpose"]
        if purpose == "cohost":
            require_course_creator(request.user, classroom.course)
        if not classroom.is_active:
            raise ValidationError("This classroom is inactive.")
        users = get_user_model().objects.filter(is_active=True, username__icontains=query.validated_data["q"])
        if purpose == "invite":
            if classroom.course.status != "APPROVED":
                raise ValidationError("Only approved courses can invite learners.")
            # Existing members (including revoked members) cannot be invited as learners.
            users = users.exclude(pk__in=classroom.memberships.values("user_id")).exclude(
                pk__in=[request.user.pk, classroom.course.creator_id])
        else:
            users = users.exclude(pk__in=classroom.memberships.filter(
                is_active=True, role__in=[ClassroomRole.HOST, ClassroomRole.COHOST]).values("user_id"))
        return self.page(request, users.order_by(Lower("username"), "pk"), ClassroomUserSearchSerializer)

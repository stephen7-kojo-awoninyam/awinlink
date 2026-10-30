from api.pagination import PagedAPIView
from api.search import BoundedSearchFilter, filter_parent
from django.utils.decorators import method_decorator
from .visibility import visible_events_for
from django.views.decorators.cache import never_cache
from organizations.models import Organization
from organizations.permissions import OrganizationCapability, get_request_organization, require_active_organization, require_user_organization_active
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .services import CertificateGenerator
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    EventCategory,
    Event,
    EventRegistration,
    EventFeedback,
    EventCertificate,
    EventMedia,
)

from .serializers import (
    EventCategorySerializer,
    EventSerializer,
    EventRegistrationSerializer,
    EventFeedbackSerializer,
    EventCertificateSerializer,
    EventMediaSerializer,
)


# ============================================================
# EVENT CATEGORIES
# ============================================================

@method_decorator(never_cache, name='dispatch')
class EventCategoryListAPIView(generics.ListAPIView):

    permission_classes = [IsAuthenticated]

    queryset = EventCategory.objects.all().order_by("name")

    serializer_class = EventCategorySerializer


# ============================================================
# EVENT LIST
# ============================================================

@method_decorator(never_cache, name='dispatch')
class EventListAPIView(generics.ListAPIView):
    filter_backends = [BoundedSearchFilter]
    search_fields = ['title', 'description', 'organizer__name', 'category__name', 'location']

    permission_classes = [IsAuthenticated]

    serializer_class = EventSerializer

    def get_queryset(self):

        return visible_events_for(self.request.user).filter(
            organizer__status="ACTIVE",
            status="PUBLISHED"
        ).select_related(
            "organizer",
            "category",
        ).order_by(
            "-created_at"
        )


# ============================================================
# EVENT DETAIL
# ============================================================

@method_decorator(never_cache, name='dispatch')
class EventDetailAPIView(generics.RetrieveAPIView):

    permission_classes = [IsAuthenticated]

    serializer_class = EventSerializer

    lookup_url_kwarg = "event_id"

    def get_queryset(self):

        return visible_events_for(self.request.user).select_related(
            "organizer",
            "category",
        )


# ============================================================
# CREATE EVENT
# ============================================================

@method_decorator(never_cache, name='dispatch')
class EventCreateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):


        try:
            organization = get_request_organization(
                request, OrganizationCapability.MANAGE_EVENTS,
            )
        except Organization.DoesNotExist:
            if request.user.role != "ORGANIZATION":
                return Response(
                    {"detail": "Only organization accounts can create events."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            return Response(
                {"detail": "Organization profile not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if organization is None:

            return Response(
                {
                    "detail": (
                        "Organization profile not found."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = EventSerializer(
            data=request.data
        )

        if serializer.is_valid():

            event = serializer.save(
                organizer=organization
            )

            return Response(
                EventSerializer(event).data,
                status=status.HTTP_201_CREATED
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


# ============================================================
# UPDATE EVENT
# ============================================================

@method_decorator(never_cache, name='dispatch')
class EventUpdateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def put(self, request, event_id):

        event = get_object_or_404(
            visible_events_for(self.request.user),
            id=event_id
        )


        organization = get_request_organization(request, OrganizationCapability.MANAGE_EVENTS, organization=event.organizer)

        if organization != event.organizer:

            return Response(
                {
                    "detail": (
                        "You do not have permission "
                        "to update this event."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = EventSerializer(
            event,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():
            from media_erasure.services import save_instance_with_media_retention
            save_instance_with_media_retention(event, serializer.save, requested_by_id=request.user.pk)

            return Response(
                serializer.data
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


# ============================================================
# DELETE EVENT
# ============================================================

@method_decorator(never_cache, name='dispatch')
class EventDeleteAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def delete(self, request, event_id):

        event = get_object_or_404(
            visible_events_for(self.request.user),
            id=event_id
        )


        organization = get_request_organization(request, OrganizationCapability.MANAGE_EVENTS, organization=event.organizer)

        if organization != event.organizer:

            return Response(
                {
                    "detail": (
                        "You do not have permission "
                        "to delete this event."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        from media_erasure.services import delete_event_with_retention
        delete_event_with_retention(event, requested_by_id=request.user.pk)

        return Response(
            {
                "detail": "Event deleted successfully."
            },
            status=status.HTTP_204_NO_CONTENT
        )


# ============================================================
# REGISTER FOR EVENT
# ============================================================

@method_decorator(never_cache, name='dispatch')
class EventCancelRegistrationAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, event_id):

        # ==========================================
        # ONLY TALENTS CAN CANCEL THEIR REGISTRATION
        # ==========================================

        if request.user.role != "ATHLETE":
            return Response(
                {
                    "detail": (
                        "Only ATHLETE users can cancel "
                        "event registrations."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # ==========================================
        # GET TALENT PROFILE
        # ==========================================

        try:
            talent = request.user.talent_profile
        except Exception:
            return Response(
                {
                    "detail": "Talent profile not found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # ==========================================
        # GET REGISTRATION
        # ==========================================

        registration = get_object_or_404(
            EventRegistration,
            event_id=event_id,
            talent=talent,
        )

        # ==========================================
        # VALIDATE STATUS
        # ==========================================

        if registration.status == "CANCELLED":
            return Response(
                {
                    "detail": "This registration is already cancelled."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if registration.status == "ATTENDED":
            return Response(
                {
                    "detail": (
                        "An attended registration cannot be cancelled."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if registration.status == "REJECTED":
            return Response(
                {
                    "detail": (
                        "A rejected registration cannot be cancelled."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ==========================================
        # CANCEL REGISTRATION
        # ==========================================

        registration.status = "CANCELLED"

        registration.save(
            update_fields=["status"]
        )

        return Response(
            {
                "message": "Registration cancelled successfully.",
                "registration": EventRegistrationSerializer(
                    registration
                ).data,
            },
            status=status.HTTP_200_OK,
        )
        
        
@method_decorator(never_cache, name='dispatch')
class EventRegisterAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, event_id):

        # ==========================================
        # ONLY TALENTS CAN REGISTER
        # ==========================================

        if request.user.role != "ATHLETE":
            return Response(
                {
                    "detail": (
                        "Only ATHLETE users can register "
                        "for events."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # ==========================================
        # GET TALENT PROFILE
        # ==========================================

        try:
            talent = request.user.talent_profile
        except Exception:
            return Response(
                {
                    "detail": "Talent profile not found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # ==========================================
        # GET EVENT
        # ==========================================

        event = get_object_or_404(
            visible_events_for(self.request.user),
            id=event_id,
        )
        require_active_organization(event.organizer)

        # ==========================================
        # EVENT MUST BE PUBLISHED
        # ==========================================

        if event.status != "PUBLISHED":
            return Response(
                {
                    "detail": (
                        "Registration is only available "
                        "for published events."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ==========================================
        # CHECK REGISTRATION DEADLINE
        # ==========================================

        if (
            event.registration_deadline
            and timezone.now() > event.registration_deadline
        ):
            return Response(
                {
                    "detail": "The registration deadline has passed."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ==========================================
        # CHECK CAPACITY
        # ==========================================

        if event.capacity and event.capacity > 0:

            registration_count = EventRegistration.objects.filter(
                event=event,
                status__in=[
                    "REGISTERED",
                    "APPROVED",
                ],
            ).count()

            if registration_count >= event.capacity:
                return Response(
                    {
                        "detail": "This event is already full."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # ==========================================
        # CHECK EXISTING REGISTRATION
        # ==========================================

        registration = EventRegistration.objects.filter(
            event=event,
            talent=talent,
        ).first()

        # ==========================================
        # ACTIVE REGISTRATION ALREADY EXISTS
        # ==========================================

        if registration and registration.status in [
            "REGISTERED",
            "APPROVED",
            "ATTENDED",
        ]:
            return Response(
                {
                    "detail": (
                        "You already have an active registration "
                        "for this event."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ==========================================
        # REACTIVATE CANCELLED REGISTRATION
        # ==========================================

        if registration and registration.status == "CANCELLED":

            registration.status = "REGISTERED"
            registration.registered_at = timezone.now()
            registration.attendance_marked = False
            registration.attendance_time = None

            registration.save(
                update_fields=[
                    "status",
                    "registered_at",
                    "attendance_marked",
                    "attendance_time",
                ]
            )

        # ==========================================
        # CREATE NEW REGISTRATION
        # ==========================================

        else:

            registration = EventRegistration.objects.create(
                event=event,
                talent=talent,
                status="REGISTERED",
            )

        serializer = EventRegistrationSerializer(
            registration
        )

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
        )        


# ============================================================
# MY EVENT REGISTRATIONS
# ============================================================

@method_decorator(never_cache, name='dispatch')
class MyEventRegistrationsAPIView(generics.ListAPIView):

    permission_classes = [IsAuthenticated]

    serializer_class = EventRegistrationSerializer

    def get_queryset(self):

        if self.request.user.role != "ATHLETE":

            return EventRegistration.objects.none()

        talent = getattr(
            self.request.user,
            "talent_profile",
            None
        )

        if talent is None:

            return EventRegistration.objects.none()

        return filter_parent(self.request, EventRegistration.objects.filter(
            talent=talent, event__in=visible_events_for(self.request.user)
        ).select_related(
            "event",
            "talent__user",
        ), 'event')


@method_decorator(never_cache, name='dispatch')
class EventRegistrationListAPIView(PagedAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        # ==========================================
        # ONLY ORGANIZATIONS CAN VIEW REGISTRATIONS
        # ==========================================


        # ==========================================
        # GET ORGANIZATION PROFILE
        # ==========================================

        try:
            organization = get_request_organization(request, OrganizationCapability.VIEW_EVENTS)
        except Organization.DoesNotExist:
            if request.user.role != "ORGANIZATION":
                return Response(
                    {"detail": "Only ORGANIZATION users can view event registrations."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            return Response(
                {"detail": "Organization profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # ==========================================
        # GET REGISTRATIONS FOR ORGANIZATION EVENTS
        # ==========================================

        registrations = (
            EventRegistration.objects
            .filter(event__organizer=organization)
            .select_related(
                "event",
                "talent",
                "talent__user",
            )
            .order_by("-registered_at")
        )

        serializer = EventRegistrationSerializer(
            self.page(request, registrations),
            many=True,
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )



# ============================================================
# EVENT REGISTRATIONS
# ORGANIZATION VIEW
# ============================================================

@method_decorator(never_cache, name='dispatch')
class EventRegistrationStatusAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, registration_id):

        # ==========================================
        # ONLY ORGANIZATIONS CAN MANAGE REGISTRATIONS
        # ==========================================


        # ==========================================
        # GET ORGANIZATION PROFILE
        # ==========================================

        try:
            organization = get_request_organization(request, OrganizationCapability.MANAGE_EVENTS)
        except Organization.DoesNotExist:
            if request.user.role != "ORGANIZATION":
                return Response(
                    {"detail": "Only ORGANIZATION users can update registration status."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            return Response(
                {"detail": "Organization profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # ==========================================
        # GET REGISTRATION
        # ==========================================

        registration = get_object_or_404(
            EventRegistration.objects.select_related(
                "event",
                "talent",
                "talent__user",
            ),
            id=registration_id,
            event__organizer=organization,
        )

        # ==========================================
        # GET NEW STATUS
        # ==========================================

        new_status = request.data.get("status")

        if new_status not in ["APPROVED", "REJECTED"]:
            return Response(
                {
                    "detail": (
                        "Status must be either APPROVED or REJECTED."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ==========================================
        # PREVENT CHANGING COMPLETED REGISTRATIONS
        # ==========================================

        if registration.status in [
            "ATTENDED",
            "CANCELLED",
        ]:
            return Response(
                {
                    "detail": (
                        f"A registration with status "
                        f"{registration.status} cannot be changed."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ==========================================
        # UPDATE STATUS
        # ==========================================

        registration.status = new_status
        registration.save(update_fields=["status"])

        return Response(
            EventRegistrationSerializer(registration).data,
            status=status.HTTP_200_OK,
        )

# ============================================================
# MARK ATTENDANCE
# ============================================================

@method_decorator(never_cache, name='dispatch')
class EventAttendanceAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, registration_id):

        # ==========================================
        # ONLY ORGANIZATIONS CAN MARK ATTENDANCE
        # ==========================================


        # ==========================================
        # GET ORGANIZATION PROFILE
        # ==========================================

        try:
            organization = get_request_organization(request, OrganizationCapability.MANAGE_EVENTS)
        except Organization.DoesNotExist:
            if request.user.role != "ORGANIZATION":
                return Response(
                    {"detail": "Only ORGANIZATION users can mark event attendance."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            return Response(
                {"detail": "Organization profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # ==========================================
        # GET REGISTRATION
        # ==========================================

        registration = get_object_or_404(
            EventRegistration.objects.select_related(
                "event",
                "talent",
                "talent__user",
            ),
            id=registration_id,
            event__organizer=organization,
        )

        # ==========================================
        # VALIDATE REGISTRATION STATUS
        # ==========================================

        if registration.status != "APPROVED":
            return Response(
                {
                    "detail": (
                        "Only APPROVED registrations can be marked "
                        "as attended."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ==========================================
        # MARK ATTENDANCE
        # ==========================================

        registration.attendance_marked = True
        registration.attendance_time = timezone.now()
        registration.status = "ATTENDED"

        registration.save(
            update_fields=[
                "attendance_marked",
                "attendance_time",
                "status",
            ]
        )

        # ==========================================
        # GENERATE CERTIFICATE
        # ==========================================

        certificate = CertificateGenerator.generate(
            event=registration.event,
            talent=registration.talent,
        )

        # ==========================================
        # RETURN RESPONSE
        # ==========================================

        response_data = {
            "message": "Attendance marked successfully.",
            "registration": EventRegistrationSerializer(
                registration
            ).data,
        }

        if certificate:
            response_data["certificate"] = EventCertificateSerializer(
                certificate
            ).data

        return Response(
            response_data,
            status=status.HTTP_200_OK,
        )


# ============================================================
# EVENT FEEDBACK
# ============================================================

@method_decorator(never_cache, name='dispatch')
class EventFeedbackCreateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, event_id):

        event = get_object_or_404(
            visible_events_for(self.request.user),
            id=event_id
        )

        registration = EventRegistration.objects.filter(
            event=event,
            talent__user=request.user,
            status="ATTENDED",
            attendance_marked=True,
        ).first()

        if registration is None:

            return Response(
                {
                    "detail": (
                        "You can only review an "
                        "event you attended."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = EventFeedbackSerializer(
            data=request.data
        )

        if serializer.is_valid():

            feedback = serializer.save(
                event=event,
                reviewer=request.user
            )

            return Response(
                EventFeedbackSerializer(
                    feedback
                ).data,
                status=status.HTTP_201_CREATED
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


# ============================================================
# EVENT FEEDBACK LIST
# ============================================================

@method_decorator(never_cache, name='dispatch')
class EventFeedbackListAPIView(generics.ListAPIView):

    permission_classes = [IsAuthenticated]

    serializer_class = EventFeedbackSerializer

    def get_queryset(self):
        event = get_object_or_404(visible_events_for(self.request.user), pk=self.kwargs['event_id'])
        return EventFeedback.objects.filter(
            event=event
        ).select_related(
            "reviewer"
        )


# ============================================================
# EVENT CERTIFICATES
# ============================================================

@method_decorator(never_cache, name='dispatch')
class MyEventCertificatesAPIView(generics.ListAPIView):

    permission_classes = [IsAuthenticated]

    serializer_class = EventCertificateSerializer

    def get_queryset(self):

        if self.request.user.role != "ATHLETE":

            return EventCertificate.objects.none()

        talent = getattr(
            self.request.user,
            "talent_profile",
            None
        )

        if talent is None:

            return EventCertificate.objects.none()

        return EventCertificate.objects.filter(
            talent=talent
        ).select_related(
            "event",
            "issued_by",
            "talent__user",
        )


# ============================================================
# VERIFY CERTIFICATE
# ============================================================

@method_decorator(never_cache, name='dispatch')
class EventCertificateVerifyAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, certificate_code):

        certificate = get_object_or_404(
            EventCertificate,
            certificate_code=certificate_code
        )

        return Response(
            EventCertificateSerializer(
                certificate, context={'request': request}
            ).data
        )


# ============================================================
# EVENT MEDIA
# ============================================================

@method_decorator(never_cache, name='dispatch')
class EventMediaListAPIView(generics.ListAPIView):

    permission_classes = [IsAuthenticated]

    serializer_class = EventMediaSerializer

    def get_queryset(self):
        event = get_object_or_404(visible_events_for(self.request.user), pk=self.kwargs['event_id'])
        return EventMedia.objects.filter(
            event=event
        ).select_related(
            "event",
            "uploaded_by",
        )


# ============================================================
# UPLOAD EVENT MEDIA
# ============================================================

@method_decorator(never_cache, name='dispatch')
class EventMediaCreateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, event_id):


        try:
            organization = get_request_organization(
                request, OrganizationCapability.MANAGE_EVENTS,
            )
        except Organization.DoesNotExist:
            if request.user.role != "ORGANIZATION":
                return Response(
                    {"detail": "Only organization accounts can upload event media."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            organization = None

        event = get_object_or_404(
            visible_events_for(self.request.user),
            id=event_id,
            organizer=organization
        )

        serializer = EventMediaSerializer(
            data=request.data
        )

        if serializer.is_valid():

            media = serializer.save(
                event=event,
                uploaded_by=organization
            )

            return Response(
                EventMediaSerializer(
                    media
                ).data,
                status=status.HTTP_201_CREATED
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


@method_decorator(never_cache, name='dispatch')
class MyOrganizationEventsAPIView(PagedAPIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        try:
            organization = get_request_organization(
                request, OrganizationCapability.VIEW_EVENTS,
            )
        except Organization.DoesNotExist:
            if request.user.role != "ORGANIZATION":
                return Response(
                    {"detail": "Only organizations can view managed events."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            return Response([])
        events = visible_events_for(self.request.user).filter(
            organizer=organization
        ).select_related("organizer", "category").order_by("-created_at")
        return Response(EventSerializer(self.page(request, events), many=True).data)

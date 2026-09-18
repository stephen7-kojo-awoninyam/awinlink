from django.contrib.auth import authenticate
from django.db import models
from talents.models import TalentProfile, RoleModelAssignment
from talents.services import FollowerAnalyticsService
from .serializers import EventRecommendationSerializer, RoleModelAssignmentSerializer
from accounts.models import User
from organizations.models import Organization
from opportunities.models import Opportunity
from talents.models import TalentProfile
from invitations.models import Invitation
from connections.models import (
    Connection,
    Follow,
    OrganizationFollow,
)
from applications.models import Application
from shortlists.models import Shortlist
from recruitment.models import RecruitmentStage
from notifications.models import Notification

from analytics.models import (
    TalentScore,
    TalentProfileView,
    RecommendationHistory,
)

from analytics.services import TalentCalculator
from recommendations.services import RecommendationEngine

from rest_framework import status
from rest_framework.permissions import (
    AllowAny,
    IsAuthenticated,
)
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import (
    UserSerializer,
    TalentProfileSerializer,
    OrganizationSerializer,
    OpportunitySerializer,
    OpportunityCreateSerializer,
    ApplicationSerializer,
    ApplicationCreateSerializer,
    ShortlistSerializer,
    RecruitmentStageSerializer,
    RecommendationSerializer,
    RecommendationHistorySerializer,
    TalentScoreSerializer,
    TalentProfileViewSerializer,
    InvitationSerializer,
    ConnectionSerializer,
    FollowSerializer,
    OrganizationFollowSerializer,
    NotificationSerializer,
    ShortlistCreateSerializer,
    RecruitmentStageCreateSerializer,
    InvitationCreateSerializer,
    RoleModelRecommendationSerializer,
    CourseRecommendationSerializer,
    EventRecommendationSerializer,
    serializers,
)

# =====================================================
# LOGIN
# =====================================================

class LoginAPIView(APIView):

    permission_classes = [AllowAny]

    def post(self, request):

        username = request.data.get("username")
        password = request.data.get("password")

        if not username or not password:

            return Response(
                {
                    "detail": "Username and password are required."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        user = authenticate(
            username=username,
            password=password
        )

        if user is None:

            return Response(
                {
                    "detail": "Invalid username or password."
                },
                status=status.HTTP_401_UNAUTHORIZED
            )

        if not user.is_active:

            return Response(
                {
                    "detail": "This account is inactive."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "user": UserSerializer(user).data,
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            },
            status=status.HTTP_200_OK
        )


# =====================================================
# CURRENT USER
# =====================================================

class MeAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        return Response(
            UserSerializer(request.user).data,
            status=status.HTTP_200_OK
        )


# =====================================================
# TALENT LIST API
# =====================================================

class TalentListAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        talents = (
            TalentProfile.objects
            .select_related("user")
            .prefetch_related(
                "domains",
                "skills",
                "achievements",
                "certifications",
                "experiences",
            )
        )

        serializer = TalentProfileSerializer(
            talents,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )


# =====================================================
# TALENT DETAIL API
# =====================================================

class TalentDetailAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, talent_id):

        try:

            talent = (
                TalentProfile.objects
                .select_related("user")
                .prefetch_related(
                    "domains",
                    "skills",
                    "achievements",
                    "certifications",
                    "experiences",
                )
                .get(id=talent_id)
            )

        except TalentProfile.DoesNotExist:

            return Response(
                {
                    "detail": "Talent profile not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = TalentProfileSerializer(
            talent
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )


# =====================================================
# MY TALENT PROFILE
# =====================================================

class MyTalentProfileAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        try:

            talent = (
                TalentProfile.objects
                .select_related("user")
                .prefetch_related(
                    "domains",
                    "skills",
                    "achievements",
                    "certifications",
                    "experiences",
                )
                .get(
                    user=request.user
                )
            )

        except TalentProfile.DoesNotExist:

            return Response(
                {
                    "detail":
                    "You do not have a talent profile."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = TalentProfileSerializer(
            talent
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )


# =====================================================
# ORGANIZATION LIST API
# =====================================================

class OrganizationListAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        organizations = (
            Organization.objects
            .select_related(
                "category",
                "domain",
                "sports_profile",
                "sports_profile__sport",
            )
            .prefetch_related(
                "followers",
            )
            .all()
        )

        serializer = OrganizationSerializer(
            organizations,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )


# =====================================================
# ORGANIZATION DETAIL API
# =====================================================

class OrganizationDetailAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, organization_id):

        try:

            organization = (
                Organization.objects
                .select_related(
                    "category",
                    "domain",
                    "sports_profile",
                    "sports_profile__sport",
                )
                .prefetch_related(
                    "followers",
                )
                .get(
                    id=organization_id
                )
            )

        except Organization.DoesNotExist:

            return Response(
                {
                    "detail": "Organization not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = OrganizationSerializer(
            organization
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )


# =====================================================
# MY ORGANIZATION API
# =====================================================

class MyOrganizationAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        try:

            organization = (
                Organization.objects
                .select_related(
                    "category",
                    "domain",
                    "sports_profile",
                    "sports_profile__sport",
                )
                .prefetch_related(
                    "followers",
                )
                .get(
                    user=request.user
                )
            )

        except Organization.DoesNotExist:

            return Response(
                {
                    "detail":
                    "You do not have an organization profile."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = OrganizationSerializer(
            organization
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )


# =====================================================
# OPPORTUNITY LIST API
# =====================================================

class OpportunityListAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        opportunities = (
            Opportunity.objects
            .select_related(
                "organization",
                "domain",
            )
            .prefetch_related(
                "skills",
                "requirements",
                "requirements__skill",
            )
            .filter(
                active=True
            )
            .order_by(
                "-created_at"
            )
        )

        serializer = OpportunitySerializer(
            opportunities,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )


# =====================================================
# OPPORTUNITY DETAIL API
# =====================================================

class OpportunityDetailAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, opportunity_id):

        try:

            opportunity = (
                Opportunity.objects
                .select_related(
                    "organization",
                    "domain",
                )
                .prefetch_related(
                    "skills",
                    "requirements",
                    "requirements__skill",
                )
                .get(
                    id=opportunity_id
                )
            )

        except Opportunity.DoesNotExist:

            return Response(
                {
                    "detail": "Opportunity not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = OpportunitySerializer(
            opportunity
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
        
        
# =====================================================
# CREATE OPPORTUNITY API
# =====================================================

class OpportunityCreateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        # ---------------------------------------------
        # FIND ORGANIZATION BELONGING TO USER
        # ---------------------------------------------

        try:

            organization = Organization.objects.get(
                user=request.user
            )

        except Organization.DoesNotExist:

            return Response(
                {
                    "detail":
                    "You do not have an organization profile."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # ---------------------------------------------
        # VALIDATE REQUEST DATA
        # ---------------------------------------------

        serializer = OpportunityCreateSerializer(
            data=request.data
        )

        if not serializer.is_valid():

            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------
        # CREATE OPPORTUNITY
        # ---------------------------------------------

        opportunity = serializer.save(
            organization=organization
        )

        # ---------------------------------------------
        # RETURN FULL OPPORTUNITY
        # ---------------------------------------------

        response_serializer = OpportunitySerializer(
            opportunity
        )

        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED
        )  
        
        
# =====================================================
# APPLICATION CREATE API
# =====================================================

class ApplicationCreateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        # ---------------------------------------------
        # Get the authenticated user's talent profile
        # ---------------------------------------------

        try:

            talent = TalentProfile.objects.get(
                user=request.user
            )

        except TalentProfile.DoesNotExist:

            return Response(
                {
                    "detail": "You do not have a talent profile."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # Validate application data
        # ---------------------------------------------

        serializer = ApplicationCreateSerializer(
            data=request.data
        )

        if not serializer.is_valid():

            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        opportunity = serializer.validated_data["opportunity"]

        # ---------------------------------------------
        # Check if opportunity is active
        # ---------------------------------------------

        if not opportunity.active:

            return Response(
                {
                    "detail": "This opportunity is no longer active."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------
        # Check for existing application
        # ---------------------------------------------

        if Application.objects.filter(
            talent=talent,
            opportunity=opportunity
        ).exists():

            return Response(
                {
                    "detail": "You have already applied for this opportunity."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------
        # Create application
        # ---------------------------------------------

        application = serializer.save(
            talent=talent
        )

        # ---------------------------------------------
        # Return created application
        # ---------------------------------------------

        response_serializer = ApplicationSerializer(
            application
        )

        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED
        )


# =====================================================
# APPLICATION LIST API
# =====================================================

class ApplicationListAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        applications = (
            Application.objects
            .select_related(
                "talent",
                "talent__user",
                "opportunity",
                "opportunity__organization",
                "opportunity__domain",
            )
            .prefetch_related(
                "opportunity__skills",
            )
            .order_by(
                "-created_at"
            )
        )

        serializer = ApplicationSerializer(
            applications,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )


# =====================================================
# APPLICATION DETAIL API
# =====================================================

class ApplicationDetailAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, application_id):

        try:

            application = (
                Application.objects
                .select_related(
                    "talent",
                    "talent__user",
                    "opportunity",
                    "opportunity__organization",
                    "opportunity__domain",
                )
                .get(
                    id=application_id
                )
            )

        except Application.DoesNotExist:

            return Response(
                {
                    "detail": "Application not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = ApplicationSerializer(
            application
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )


# =====================================================
# MY APPLICATIONS API
# =====================================================

class MyApplicationsAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        try:

            talent = TalentProfile.objects.get(
                user=request.user
            )

        except TalentProfile.DoesNotExist:

            return Response(
                {
                    "detail": "You do not have a talent profile."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        applications = (
            Application.objects
            .filter(
                talent=talent
            )
            .select_related(
                "talent",
                "talent__user",
                "opportunity",
                "opportunity__organization",
                "opportunity__domain",
            )
            .order_by(
                "-created_at"
            )
        )

        serializer = ApplicationSerializer(
            applications,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
        
# =====================================================
# SHORTLIST CREATE API
# =====================================================

class ShortlistCreateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        # ---------------------------------------------
        # Only organizations can create shortlists
        # ---------------------------------------------

        if request.user.role != "ORGANIZATION":

            return Response(
                {
                    "detail": "Only organizations can create shortlists."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # ---------------------------------------------
        # Get organization profile
        # ---------------------------------------------

        try:

            organization = request.user.organization_profile

        except Organization.DoesNotExist:

            return Response(
                {
                    "detail": "You do not have an organization profile."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # Validate data
        # ---------------------------------------------

        serializer = ShortlistCreateSerializer(
            data=request.data
        )

        if not serializer.is_valid():

            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        talent = serializer.validated_data["talent"]

        # ---------------------------------------------
        # Prevent duplicate shortlist
        # ---------------------------------------------

        if Shortlist.objects.filter(
            organization=organization,
            talent=talent
        ).exists():

            return Response(
                {
                    "detail": "This talent has already been shortlisted."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------
        # Create shortlist
        # ---------------------------------------------

        shortlist = serializer.save(
            organization=organization
        )

        # ---------------------------------------------
        # Return created shortlist
        # ---------------------------------------------

        response_serializer = ShortlistSerializer(
            shortlist
        )

        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED
        )
        
        
# =====================================================
# SHORTLIST LIST API
# =====================================================

class ShortlistListAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        # ---------------------------------------------
        # ORGANIZATION
        # ---------------------------------------------

        if request.user.role == "ORGANIZATION":

            try:

                organization = request.user.organization_profile

            except Organization.DoesNotExist:

                return Response(
                    {
                        "detail": "You do not have an organization profile."
                    },
                    status=status.HTTP_404_NOT_FOUND
                )

            shortlists = (
                Shortlist.objects
                .filter(
                    organization=organization
                )
                .select_related(
                    "organization",
                    "talent",
                    "talent__user",
                )
                .order_by(
                    "-created_at"
                )
            )

        # ---------------------------------------------
        # ADMIN
        # ---------------------------------------------

        elif request.user.role == "ADMIN":

            shortlists = (
                Shortlist.objects
                .select_related(
                    "organization",
                    "talent",
                    "talent__user",
                )
                .order_by(
                    "-created_at"
                )
            )

        # ---------------------------------------------
        # OTHER ROLES
        # ---------------------------------------------

        else:

            return Response(
                {
                    "detail": "You do not have permission to view shortlists."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = ShortlistSerializer(
            shortlists,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
        
# =====================================================
# SHORTLIST DETAIL API
# =====================================================

class ShortlistDetailAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, shortlist_id):

        try:

            shortlist = (
                Shortlist.objects
                .select_related(
                    "organization",
                    "talent",
                    "talent__user",
                )
                .get(
                    id=shortlist_id
                )
            )

        except Shortlist.DoesNotExist:

            return Response(
                {
                    "detail": "Shortlist not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # ORGANIZATION
        # ---------------------------------------------

        if request.user.role == "ORGANIZATION":

            try:

                organization = request.user.organization_profile

            except Organization.DoesNotExist:

                return Response(
                    {
                        "detail": "You do not have an organization profile."
                    },
                    status=status.HTTP_404_NOT_FOUND
                )

            if shortlist.organization != organization:

                return Response(
                    {
                        "detail": "You do not have permission to view this shortlist."
                    },
                    status=status.HTTP_403_FORBIDDEN
                )

        # ---------------------------------------------
        # ADMIN
        # ---------------------------------------------

        elif request.user.role == "ADMIN":

            pass

        # ---------------------------------------------
        # OTHER ROLES
        # ---------------------------------------------

        else:

            return Response(
                {
                    "detail": "You do not have permission to view shortlists."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = ShortlistSerializer(
            shortlist
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        

# =====================================================
# MY SHORTLISTS API
# =====================================================

class MyShortlistsAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        if request.user.role != "ORGANIZATION":

            return Response(
                {
                    "detail": "Only organizations can access their shortlists."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        try:

            organization = request.user.organization_profile

        except Organization.DoesNotExist:

            return Response(
                {
                    "detail": "You do not have an organization profile."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        shortlists = (
            Shortlist.objects
            .filter(
                organization=organization
            )
            .select_related(
                "organization",
                "talent",
                "talent__user",
            )
            .order_by(
                "-created_at"
            )
        )

        serializer = ShortlistSerializer(
            shortlists,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )   
        
        
# =====================================================
# RECRUITMENT PIPELINE CREATE API
# =====================================================

class RecruitmentStageCreateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        # ---------------------------------------------
        # Only organizations can manage recruitment
        # ---------------------------------------------

        if request.user.role != "ORGANIZATION":

            return Response(
                {
                    "detail": "Only organizations can create recruitment stages."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # ---------------------------------------------
        # Get organization profile
        # ---------------------------------------------

        try:

            organization = request.user.organization_profile

        except Organization.DoesNotExist:

            return Response(
                {
                    "detail": "You do not have an organization profile."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # Validate request
        # ---------------------------------------------

        serializer = RecruitmentStageCreateSerializer(
            data=request.data
        )

        if not serializer.is_valid():

            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        talent = serializer.validated_data["talent"]
        opportunity = serializer.validated_data["opportunity"]

        # ---------------------------------------------
        # Make sure opportunity belongs to organization
        # ---------------------------------------------

        if opportunity.organization != organization:

            return Response(
                {
                    "detail": "You cannot manage recruitment for another organization's opportunity."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # ---------------------------------------------
        # Prevent duplicate pipeline entry
        # ---------------------------------------------

        if RecruitmentStage.objects.filter(
            organization=organization,
            talent=talent,
            opportunity=opportunity
        ).exists():

            return Response(
                {
                    "detail": "This talent already exists in the recruitment pipeline for this opportunity."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------
        # Create pipeline entry
        # ---------------------------------------------

        recruitment_stage = serializer.save(
            organization=organization
        )

        # ---------------------------------------------
        # Return result
        # ---------------------------------------------

        response_serializer = RecruitmentStageSerializer(
            recruitment_stage
        )

        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED
        )
        
        
# =====================================================
# RECRUITMENT PIPELINE LIST API
# =====================================================

class RecruitmentStageListAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        # ---------------------------------------------
        # ORGANIZATION
        # ---------------------------------------------

        if request.user.role == "ORGANIZATION":

            try:

                organization = request.user.organization_profile

            except Organization.DoesNotExist:

                return Response(
                    {
                        "detail": "You do not have an organization profile."
                    },
                    status=status.HTTP_404_NOT_FOUND
                )

            stages = (
                RecruitmentStage.objects
                .filter(
                    organization=organization
                )
                .select_related(
                    "organization",
                    "talent",
                    "talent__user",
                    "opportunity",
                )
                .order_by(
                    "-updated_at"
                )
            )

        # ---------------------------------------------
        # ADMIN
        # ---------------------------------------------

        elif request.user.role == "ADMIN":

            stages = (
                RecruitmentStage.objects
                .select_related(
                    "organization",
                    "talent",
                    "talent__user",
                    "opportunity",
                )
                .order_by(
                    "-updated_at"
                )
            )

        # ---------------------------------------------
        # OTHER ROLES
        # ---------------------------------------------

        else:

            return Response(
                {
                    "detail": "You do not have permission to view the recruitment pipeline."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = RecruitmentStageSerializer(
            stages,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
# =====================================================
# RECRUITMENT PIPELINE DETAIL API
# =====================================================

class RecruitmentStageDetailAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, stage_id):

        try:

            recruitment_stage = (
                RecruitmentStage.objects
                .select_related(
                    "organization",
                    "talent",
                    "talent__user",
                    "opportunity",
                )
                .get(
                    id=stage_id
                )
            )

        except RecruitmentStage.DoesNotExist:

            return Response(
                {
                    "detail": "Recruitment stage not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # ORGANIZATION
        # ---------------------------------------------

        if request.user.role == "ORGANIZATION":

            try:

                organization = request.user.organization_profile

            except Organization.DoesNotExist:

                return Response(
                    {
                        "detail": "You do not have an organization profile."
                    },
                    status=status.HTTP_404_NOT_FOUND
                )

            if recruitment_stage.organization != organization:

                return Response(
                    {
                        "detail": "You do not have permission to view this recruitment record."
                    },
                    status=status.HTTP_403_FORBIDDEN
                )

        # ---------------------------------------------
        # ADMIN
        # ---------------------------------------------

        elif request.user.role == "ADMIN":

            pass

        # ---------------------------------------------
        # OTHER ROLES
        # ---------------------------------------------

        else:

            return Response(
                {
                    "detail": "You do not have permission to view the recruitment pipeline."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = RecruitmentStageSerializer(
            recruitment_stage
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
# =====================================================
# RECRUITMENT PIPELINE UPDATE API
# =====================================================

class RecruitmentStageUpdateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def patch(self, request, stage_id):

        # ---------------------------------------------
        # Only organizations can update pipeline
        # ---------------------------------------------

        if request.user.role != "ORGANIZATION":

            return Response(
                {
                    "detail": "Only organizations can update recruitment stages."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # ---------------------------------------------
        # Get organization
        # ---------------------------------------------

        try:

            organization = request.user.organization_profile

        except Organization.DoesNotExist:

            return Response(
                {
                    "detail": "You do not have an organization profile."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # Get pipeline record
        # ---------------------------------------------

        try:

            recruitment_stage = RecruitmentStage.objects.get(
                id=stage_id
            )

        except RecruitmentStage.DoesNotExist:

            return Response(
                {
                    "detail": "Recruitment stage not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # Ownership check
        # ---------------------------------------------

        if recruitment_stage.organization != organization:

            return Response(
                {
                    "detail": "You do not have permission to update this recruitment record."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # ---------------------------------------------
        # Validate update
        # ---------------------------------------------

        allowed_fields = {
            "stage",
            "notes",
        }

        invalid_fields = set(request.data.keys()) - allowed_fields

        if invalid_fields:

            return Response(
                {
                    "detail": (
                        "You can only update: stage and notes."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------
        # Validate stage
        # ---------------------------------------------

        valid_stages = {
            choice[0]
            for choice in RecruitmentStage.STAGES
        }

        new_stage = request.data.get(
            "stage"
        )

        if new_stage is not None:

            if new_stage not in valid_stages:

                return Response(
                    {
                        "detail": "Invalid recruitment stage.",
                        "valid_stages": list(valid_stages)
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            recruitment_stage.stage = new_stage

        # ---------------------------------------------
        # Update notes
        # ---------------------------------------------

        if "notes" in request.data:

            recruitment_stage.notes = request.data["notes"]

        recruitment_stage.save()

        # ---------------------------------------------
        # Return updated record
        # ---------------------------------------------

        serializer = RecruitmentStageSerializer(
            recruitment_stage
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )   
        
        
        
# =====================================================
# GENERATE RECOMMENDATIONS API
# =====================================================

class RecommendationGenerateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, opportunity_id):

        # ---------------------------------------------
        # Only organizations can generate recommendations
        # ---------------------------------------------

        if request.user.role != "ORGANIZATION":

            return Response(
                {
                    "detail": "Only organizations can generate recommendations."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # ---------------------------------------------
        # Get organization
        # ---------------------------------------------

        try:

            organization = request.user.organization_profile

        except Organization.DoesNotExist:

            return Response(
                {
                    "detail": "You do not have an organization profile."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # Get opportunity
        # ---------------------------------------------

        try:

            opportunity = Opportunity.objects.get(
                id=opportunity_id
            )

        except Opportunity.DoesNotExist:

            return Response(
                {
                    "detail": "Opportunity not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # Ownership check
        # ---------------------------------------------

        if opportunity.organization != organization:

            return Response(
                {
                    "detail": (
                        "You cannot generate recommendations "
                        "for another organization's opportunity."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # ---------------------------------------------
        # Generate recommendations
        # ---------------------------------------------

        recommendations = (
            RecommendationEngine.generate_for_organization(
                opportunity
            )
        )

        results = []

        for recommendation in recommendations:

            talent = recommendation.talent

            results.append(
                {
                    "talent_id": talent.id,

                    "talent_name": (
                        talent.user.get_full_name()
                        or talent.user.username
                    ),

                    "talent_username": (
                        talent.user.username
                    ),

                    "score": float(
                        recommendation.score
                    ),

                    "reasons": (
                        RecommendationEngine.explain_match(
                            talent,
                            opportunity
                        )
                    ),
                }
            )

        serializer = RecommendationSerializer(
            results,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
        
# =====================================================
# RECOMMENDATIONS LIST API
# =====================================================

class RecommendationListAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, opportunity_id):

        # ---------------------------------------------
        # Only organizations can view recommendations
        # ---------------------------------------------

        if request.user.role != "ORGANIZATION":

            return Response(
                {
                    "detail": "Only organizations can view recommendations."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # ---------------------------------------------
        # Get organization
        # ---------------------------------------------

        try:

            organization = request.user.organization_profile

        except Organization.DoesNotExist:

            return Response(
                {
                    "detail": "You do not have an organization profile."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # Get opportunity
        # ---------------------------------------------

        try:

            opportunity = Opportunity.objects.get(
                id=opportunity_id
            )

        except Opportunity.DoesNotExist:

            return Response(
                {
                    "detail": "Opportunity not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # Ownership check
        # ---------------------------------------------

        if opportunity.organization != organization:

            return Response(
                {
                    "detail": (
                        "You do not have permission to view "
                        "recommendations for this opportunity."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # ---------------------------------------------
        # Get saved recommendations
        # ---------------------------------------------

        recommendations = (
            RecommendationHistory.objects
            .filter(
                organization=organization,
                opportunity=opportunity
            )
            .select_related(
                "talent",
                "talent__user",
            )
            .order_by(
                "-score"
            )
        )

        results = []

        for recommendation in recommendations:

            talent = recommendation.talent

            results.append(
                {
                    "talent_id": talent.id,

                    "talent_name": (
                        talent.user.get_full_name()
                        or talent.user.username
                    ),

                    "talent_username": (
                        talent.user.username
                    ),

                    "score": float(
                        recommendation.score
                    ),

                    "reasons": (
                        RecommendationEngine.explain_match(
                            talent,
                            opportunity
                        )
                    ),
                }
            )

        serializer = RecommendationSerializer(
            results,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )      
        
        
# =====================================================
# TALENT ANALYTICS API
# =====================================================

class TalentAnalyticsAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        if request.user.role != "ATHLETE":

            return Response(
                {
                    "detail": "Only athletes can access talent analytics."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        try:

            talent = TalentProfile.objects.get(
                user=request.user
            )

        except TalentProfile.DoesNotExist:

            return Response(
                {
                    "detail": "You do not have a talent profile."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # Calculate/update score
        # ---------------------------------------------

        talent_score = TalentCalculator.update_score(
            talent
        )

        serializer = TalentScoreSerializer(
            talent_score
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
# =====================================================
# RECOMMENDATION HISTORY API
# =====================================================

class RecommendationHistoryAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        if request.user.role == "ORGANIZATION":

            try:

                organization = request.user.organization_profile

            except Organization.DoesNotExist:

                return Response(
                    {
                        "detail": (
                            "You do not have an organization profile."
                        )
                    },
                    status=status.HTTP_404_NOT_FOUND
                )

            history = (
                RecommendationHistory.objects
                .filter(
                    organization=organization
                )
                .select_related(
                    "organization",
                    "talent",
                    "talent__user",
                    "opportunity",
                )
                .order_by(
                    "-score"
                )
            )

        elif request.user.role == "ADMIN":

            history = (
                RecommendationHistory.objects
                .select_related(
                    "organization",
                    "talent",
                    "talent__user",
                    "opportunity",
                )
                .order_by(
                    "-score"
                )
            )

        else:

            return Response(
                {
                    "detail": (
                        "You do not have permission "
                        "to view recommendation history."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = RecommendationHistorySerializer(
            history,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
# =====================================================
# TALENT PROFILE VIEWS API
# =====================================================

class TalentProfileViewsAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        if request.user.role != "ATHLETE":

            return Response(
                {
                    "detail": (
                        "Only athletes can access "
                        "their profile view analytics."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        try:

            talent = TalentProfile.objects.get(
                user=request.user
            )

        except TalentProfile.DoesNotExist:

            return Response(
                {
                    "detail": "You do not have a talent profile."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        views = (
            TalentProfileView.objects
            .filter(
                talent=talent
            )
            .select_related(
                "talent",
                "viewer",
            )
            .order_by(
                "-created_at"
            )
        )

        serializer = TalentProfileViewSerializer(
            views,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )    
        
# =====================================================
# ORGANIZATION ANALYTICS API
# =====================================================

class OrganizationAnalyticsAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        if request.user.role != "ORGANIZATION":

            return Response(
                {
                    "detail": (
                        "Only organizations can access "
                        "organization analytics."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        try:

            organization = request.user.organization_profile

        except Organization.DoesNotExist:

            return Response(
                {
                    "detail": "You do not have an organization profile."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # Recommendation statistics
        # ---------------------------------------------

        recommendations = RecommendationHistory.objects.filter(
            organization=organization
        )

        total_recommendations = recommendations.count()

        # ---------------------------------------------
        # Applications
        # ---------------------------------------------

        applications = Application.objects.filter(
            opportunity__organization=organization
        )

        total_applications = applications.count()

        # ---------------------------------------------
        # Shortlists
        # ---------------------------------------------

        shortlists = Shortlist.objects.filter(
            organization=organization
        )

        total_shortlists = shortlists.count()

        # ---------------------------------------------
        # Recruitment pipeline
        # ---------------------------------------------

        recruitment = RecruitmentStage.objects.filter(
            organization=organization
        )

        total_candidates = recruitment.count()

        selected_candidates = recruitment.filter(
            stage="SELECTED"
        ).count()

        rejected_candidates = recruitment.filter(
            stage="REJECTED"
        ).count()

        return Response(
            {
                "organization_id": organization.id,

                "recommendations": {
                    "total": total_recommendations,
                },

                "applications": {
                    "total": total_applications,
                },

                "shortlists": {
                    "total": total_shortlists,
                },

                "recruitment": {
                    "total_candidates": total_candidates,
                    "selected": selected_candidates,
                    "rejected": rejected_candidates,
                },
            },
            status=status.HTTP_200_OK
        )
        
# =====================================================
# INVITATION CREATE API
# =====================================================

class InvitationCreateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        # ---------------------------------------------
        # Only organizations can send invitations
        # ---------------------------------------------

        if request.user.role != "ORGANIZATION":

            return Response(
                {
                    "detail": "Only organizations can send invitations."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # ---------------------------------------------
        # Get organization
        # ---------------------------------------------

        try:

            organization = request.user.organization_profile

        except Organization.DoesNotExist:

            return Response(
                {
                    "detail": "You do not have an organization profile."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # Validate request
        # ---------------------------------------------

        serializer = InvitationCreateSerializer(
            data=request.data
        )

        if not serializer.is_valid():

            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        talent = serializer.validated_data["talent"]
        opportunity = serializer.validated_data["opportunity"]

        # ---------------------------------------------
        # Opportunity ownership
        # ---------------------------------------------

        if opportunity.organization != organization:

            return Response(
                {
                    "detail": (
                        "You cannot send an invitation "
                        "for another organization's opportunity."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # ---------------------------------------------
        # Prevent duplicate pending invitation
        # ---------------------------------------------

        if Invitation.objects.filter(
            organization=organization,
            talent=talent,
            opportunity=opportunity,
            status="PENDING"
        ).exists():

            return Response(
                {
                    "detail": (
                        "A pending invitation already exists "
                        "for this talent and opportunity."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------
        # Create invitation
        # ---------------------------------------------

        invitation = serializer.save(
            organization=organization
        )

        # ---------------------------------------------
        # Return invitation
        # ---------------------------------------------

        response_serializer = InvitationSerializer(
            invitation
        )

        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED
        )
        
        
# =====================================================
# SENT INVITATIONS API
# =====================================================

class SentInvitationsAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        if request.user.role != "ORGANIZATION":

            return Response(
                {
                    "detail": (
                        "Only organizations can view "
                        "sent invitations."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        try:

            organization = request.user.organization_profile

        except Organization.DoesNotExist:

            return Response(
                {
                    "detail": "You do not have an organization profile."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        invitations = (
            Invitation.objects
            .filter(
                organization=organization
            )
            .select_related(
                "organization",
                "talent",
                "talent__user",
                "opportunity",
            )
            .order_by(
                "-created_at"
            )
        )

        serializer = InvitationSerializer(
            invitations,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
        
        
# =====================================================
# RECEIVED INVITATIONS API
# =====================================================

class ReceivedInvitationsAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        if request.user.role != "ATHLETE":

            return Response(
                {
                    "detail": (
                        "Only athletes can view "
                        "received invitations."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        try:

            talent = TalentProfile.objects.get(
                user=request.user
            )

        except TalentProfile.DoesNotExist:

            return Response(
                {
                    "detail": "You do not have a talent profile."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        invitations = (
            Invitation.objects
            .filter(
                talent=talent
            )
            .select_related(
                "organization",
                "talent",
                "talent__user",
                "opportunity",
            )
            .order_by(
                "-created_at"
            )
        )

        serializer = InvitationSerializer(
            invitations,
            many=True
        )

        return Response(
            serializer.data,
            many=False,
            status=status.HTTP_200_OK
        )
        
        
        
        
# =====================================================
# INVITATION DETAIL API
# =====================================================

class InvitationDetailAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, invitation_id):

        try:

            invitation = (
                Invitation.objects
                .select_related(
                    "organization",
                    "talent",
                    "talent__user",
                    "opportunity",
                )
                .get(
                    id=invitation_id
                )
            )

        except Invitation.DoesNotExist:

            return Response(
                {
                    "detail": "Invitation not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # ORGANIZATION
        # ---------------------------------------------

        if request.user.role == "ORGANIZATION":

            try:

                organization = request.user.organization_profile

            except Organization.DoesNotExist:

                return Response(
                    {
                        "detail": (
                            "You do not have an "
                            "organization profile."
                        )
                    },
                    status=status.HTTP_404_NOT_FOUND
                )

            if invitation.organization != organization:

                return Response(
                    {
                        "detail": (
                            "You do not have permission "
                            "to view this invitation."
                        )
                    },
                    status=status.HTTP_403_FORBIDDEN
                )

        # ---------------------------------------------
        # ATHLETE
        # ---------------------------------------------

        elif request.user.role == "ATHLETE":

            try:

                talent = TalentProfile.objects.get(
                    user=request.user
                )

            except TalentProfile.DoesNotExist:

                return Response(
                    {
                        "detail": (
                            "You do not have a "
                            "talent profile."
                        )
                    },
                    status=status.HTTP_404_NOT_FOUND
                )

            if invitation.talent != talent:

                return Response(
                    {
                        "detail": (
                            "You do not have permission "
                            "to view this invitation."
                        )
                    },
                    status=status.HTTP_403_FORBIDDEN
                )

        # ---------------------------------------------
        # ADMIN
        # ---------------------------------------------

        elif request.user.role == "ADMIN":

            pass

        # ---------------------------------------------
        # OTHER ROLES
        # ---------------------------------------------

        else:

            return Response(
                {
                    "detail": (
                        "You do not have permission "
                        "to view invitations."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = InvitationSerializer(
            invitation
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )  
        
        
# =====================================================
# ACCEPT INVITATION API
# =====================================================

class InvitationAcceptAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, invitation_id):

        if request.user.role != "ATHLETE":

            return Response(
                {
                    "detail": (
                        "Only athletes can respond "
                        "to invitations."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        try:

            talent = TalentProfile.objects.get(
                user=request.user
            )

        except TalentProfile.DoesNotExist:

            return Response(
                {
                    "detail": "You do not have a talent profile."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        try:

            invitation = Invitation.objects.get(
                id=invitation_id
            )

        except Invitation.DoesNotExist:

            return Response(
                {
                    "detail": "Invitation not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # Ownership
        # ---------------------------------------------

        if invitation.talent != talent:

            return Response(
                {
                    "detail": (
                        "You cannot respond to "
                        "this invitation."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # ---------------------------------------------
        # Check current status
        # ---------------------------------------------

        if invitation.status != "PENDING":

            return Response(
                {
                    "detail": (
                        "This invitation has already "
                        "been responded to."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------
        # Accept
        # ---------------------------------------------

        invitation.accept()

        serializer = InvitationSerializer(
            invitation
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
        
# =====================================================
# DECLINE INVITATION API
# =====================================================

class InvitationDeclineAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, invitation_id):

        if request.user.role != "ATHLETE":

            return Response(
                {
                    "detail": (
                        "Only athletes can respond "
                        "to invitations."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        try:

            talent = TalentProfile.objects.get(
                user=request.user
            )

        except TalentProfile.DoesNotExist:

            return Response(
                {
                    "detail": "You do not have a talent profile."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        try:

            invitation = Invitation.objects.get(
                id=invitation_id
            )

        except Invitation.DoesNotExist:

            return Response(
                {
                    "detail": "Invitation not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        if invitation.talent != talent:

            return Response(
                {
                    "detail": (
                        "You cannot respond to "
                        "this invitation."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        if invitation.status != "PENDING":

            return Response(
                {
                    "detail": (
                        "This invitation has already "
                        "been responded to."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        invitation.decline()

        serializer = InvitationSerializer(
            invitation
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )   
        
        
# =====================================================
# CONNECTION CREATE API
# =====================================================

class ConnectionCreateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        receiver_id = request.data.get("receiver")

        # ---------------------------------------------
        # Receiver required
        # ---------------------------------------------

        if not receiver_id:

            return Response(
                {
                    "detail": "Receiver is required."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------
        # Get receiver
        # ---------------------------------------------

        try:

            receiver = User.objects.get(
                id=receiver_id
            )

        except User.DoesNotExist:

            return Response(
                {
                    "detail": "User not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # Prevent self-connection
        # ---------------------------------------------

        if receiver == request.user:

            return Response(
                {
                    "detail": (
                        "You cannot send a connection "
                        "request to yourself."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------
        # Check existing request
        # ---------------------------------------------

        existing = Connection.objects.filter(
            sender=request.user,
            receiver=receiver
        ).first()

        if existing:

            return Response(
                {
                    "detail": (
                        "A connection request already "
                        "exists between these users."
                    ),
                    "status": existing.status,
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------
        # Check reverse request
        # ---------------------------------------------

        reverse = Connection.objects.filter(
            sender=receiver,
            receiver=request.user
        ).first()

        if reverse:

            if reverse.status == "PENDING":

                return Response(
                    {
                        "detail": (
                            "This user has already sent "
                            "you a connection request. "
                            "Accept that request instead."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            if reverse.status == "ACCEPTED":

                return Response(
                    {
                        "detail": (
                            "You are already connected "
                            "with this user."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
        # ---------------------------------------------
        # Create connection
        # ---------------------------------------------

        connection = Connection.objects.create(
            sender=request.user,
            receiver=receiver,
            status="PENDING"
        )

        serializer = ConnectionSerializer(
            connection
        )

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED
        )
        
        
# =====================================================
# MY CONNECTIONS API
# =====================================================

class MyConnectionsAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        connections = (
            Connection.objects
            .filter(
                models.Q(sender=request.user) |
                models.Q(receiver=request.user),
                status="ACCEPTED"
            )
            .select_related(
                "sender",
                "receiver"
            )
            .order_by(
                "-updated_at"
            )
        )

        serializer = ConnectionSerializer(
            connections,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
        
# =====================================================
# INCOMING CONNECTION REQUESTS
# =====================================================

class IncomingConnectionsAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        connections = (
            Connection.objects
            .filter(
                receiver=request.user,
                status="PENDING"
            )
            .select_related(
                "sender",
                "receiver"
            )
            .order_by(
                "-created_at"
            )
        )

        serializer = ConnectionSerializer(
            connections,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
        
# =====================================================
# OUTGOING CONNECTION REQUESTS
# =====================================================

class OutgoingConnectionsAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        connections = (
            Connection.objects
            .filter(
                sender=request.user,
                status="PENDING"
            )
            .select_related(
                "sender",
                "receiver"
            )
            .order_by(
                "-created_at"
            )
        )

        serializer = ConnectionSerializer(
            connections,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
        
# =====================================================
# ACCEPT CONNECTION
# =====================================================

class ConnectionAcceptAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, connection_id):

        try:

            connection = (
                Connection.objects
                .select_related(
                    "sender",
                    "receiver"
                )
                .get(
                    id=connection_id
                )
            )

        except Connection.DoesNotExist:

            return Response(
                {
                    "detail": "Connection request not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # Only receiver can accept
        # ---------------------------------------------

        if connection.receiver != request.user:

            return Response(
                {
                    "detail": (
                        "Only the receiver can "
                        "accept this request."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # ---------------------------------------------
        # Check status
        # ---------------------------------------------

        if connection.status != "PENDING":

            return Response(
                {
                    "detail": (
                        "This connection request "
                        "is no longer pending."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        connection.status = "ACCEPTED"
        connection.save()

        serializer = ConnectionSerializer(
            connection
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
        
# =====================================================
# REJECT CONNECTION
# =====================================================

class ConnectionRejectAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, connection_id):

        try:

            connection = Connection.objects.get(
                id=connection_id
            )

        except Connection.DoesNotExist:

            return Response(
                {
                    "detail": "Connection request not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        if connection.receiver != request.user:

            return Response(
                {
                    "detail": (
                        "Only the receiver can "
                        "reject this request."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        if connection.status != "PENDING":

            return Response(
                {
                    "detail": (
                        "This connection request "
                        "is no longer pending."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        connection.status = "REJECTED"
        connection.save()

        serializer = ConnectionSerializer(
            connection
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
        
# =====================================================
# CANCEL CONNECTION
# =====================================================

class ConnectionCancelAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, connection_id):

        try:

            connection = Connection.objects.get(
                id=connection_id
            )

        except Connection.DoesNotExist:

            return Response(
                {
                    "detail": "Connection request not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        if connection.sender != request.user:

            return Response(
                {
                    "detail": (
                        "Only the sender can "
                        "cancel this request."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        if connection.status != "PENDING":

            return Response(
                {
                    "detail": (
                        "Only pending requests "
                        "can be cancelled."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        connection.delete()

        return Response(
            {
                "detail": "Connection request cancelled."
            },
            status=status.HTTP_200_OK
        )
        
        
# =====================================================
# CONNECTION DETAIL
# =====================================================

class ConnectionDetailAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, connection_id):

        try:

            connection = (
                Connection.objects
                .select_related(
                    "sender",
                    "receiver"
                )
                .get(
                    id=connection_id
                )
            )

        except Connection.DoesNotExist:

            return Response(
                {
                    "detail": "Connection not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # User must be involved
        # ---------------------------------------------

        if (
            connection.sender != request.user
            and
            connection.receiver != request.user
        ):

            if request.user.role != "ADMIN":

                return Response(
                    {
                        "detail": (
                            "You do not have permission "
                            "to view this connection."
                        )
                    },
                    status=status.HTTP_403_FORBIDDEN
                )

        serializer = ConnectionSerializer(
            connection
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )     
        
        
# =====================================================
# FOLLOW SERIALIZER
# =====================================================

class FollowSerializer(serializers.ModelSerializer):

    follower_id = serializers.IntegerField(
        source="follower.id",
        read_only=True
    )

    follower_username = serializers.CharField(
        source="follower.username",
        read_only=True
    )

    following_id = serializers.IntegerField(
        source="following.id",
        read_only=True
    )

    following_username = serializers.CharField(
        source="following.username",
        read_only=True
    )

    class Meta:

        model = Follow

        fields = [
            "id",
            "follower_id",
            "follower_username",
            "following_id",
            "following_username",
            "created_at",
        ]

        read_only_fields = fields
        
# =====================================================
# ORGANIZATION FOLLOW SERIALIZER
# =====================================================

class OrganizationFollowSerializer(serializers.ModelSerializer):

    user_id = serializers.IntegerField(
        source="user.id",
        read_only=True
    )

    username = serializers.CharField(
        source="user.username",
        read_only=True
    )

    organization_id = serializers.IntegerField(
        source="organization.id",
        read_only=True
    )

    organization_name = serializers.CharField(
        source="organization.name",
        read_only=True
    )

    class Meta:

        model = OrganizationFollow

        fields = [
            "id",
            "user_id",
            "username",
            "organization_id",
            "organization_name",
            "created_at",
        ]

        read_only_fields = fields
        
        
        
# =====================================================
# FOLLOW USER API
# =====================================================

class FollowUserAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, user_id):

        # ---------------------------------------------
        # Get target user
        # ---------------------------------------------

        try:

            target_user = User.objects.get(
                id=user_id
            )

        except User.DoesNotExist:

            return Response(
                {
                    "detail": "User not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # Prevent self-follow
        # ---------------------------------------------

        if target_user == request.user:

            return Response(
                {
                    "detail": "You cannot follow yourself."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------
        # Check existing follow
        # ---------------------------------------------

        if Follow.objects.filter(
            follower=request.user,
            following=target_user
        ).exists():

            return Response(
                {
                    "detail": "You are already following this user."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------
        # Create follow
        # ---------------------------------------------

        follow = Follow.objects.create(
            follower=request.user,
            following=target_user
        )

        serializer = FollowSerializer(
            follow
        )

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED
        )
        
        
# =====================================================
# UNFOLLOW USER API
# =====================================================

class UnfollowUserAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def delete(self, request, user_id):

        try:

            follow = Follow.objects.get(
                follower=request.user,
                following_id=user_id
            )

        except Follow.DoesNotExist:

            return Response(
                {
                    "detail": "You are not following this user."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        follow.delete()

        return Response(
            {
                "detail": "User unfollowed successfully."
            },
            status=status.HTTP_200_OK
        )
        
        
        
# =====================================================
# MY FOLLOWING API
# =====================================================

class MyFollowingAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        follows = (
            Follow.objects
            .filter(
                follower=request.user
            )
            .select_related(
                "following"
            )
            .order_by(
                "-created_at"
            )
        )

        serializer = FollowSerializer(
            follows,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
# =====================================================
# MY FOLLOWERS API
# =====================================================

class MyFollowersAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        follows = (
            Follow.objects
            .filter(
                following=request.user
            )
            .select_related(
                "follower"
            )
            .order_by(
                "-created_at"
            )
        )

        serializer = FollowSerializer(
            follows,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
        
# =====================================================
# FOLLOW ORGANIZATION API
# =====================================================

class FollowOrganizationAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, organization_id):

        try:

            organization = Organization.objects.get(
                id=organization_id
            )

        except Organization.DoesNotExist:

            return Response(
                {
                    "detail": "Organization not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # Check existing follow
        # ---------------------------------------------

        if OrganizationFollow.objects.filter(
            user=request.user,
            organization=organization
        ).exists():

            return Response(
                {
                    "detail": (
                        "You are already following "
                        "this organization."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------
        # Create follow
        # ---------------------------------------------

        follow = OrganizationFollow.objects.create(
            user=request.user,
            organization=organization
        )

        serializer = OrganizationFollowSerializer(
            follow
        )

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED
        )
        
        
# =====================================================
# UNFOLLOW ORGANIZATION API
# =====================================================

class UnfollowOrganizationAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def delete(self, request, organization_id):

        try:

            follow = OrganizationFollow.objects.get(
                user=request.user,
                organization_id=organization_id
            )

        except OrganizationFollow.DoesNotExist:

            return Response(
                {
                    "detail": (
                        "You are not following "
                        "this organization."
                    )
                },
                status=status.HTTP_404_NOT_FOUND
            )

        follow.delete()

        return Response(
            {
                "detail": (
                    "Organization unfollowed successfully."
                )
            },
            status=status.HTTP_200_OK
        )
        
        
# =====================================================
# MY FOLLOWED ORGANIZATIONS API
# =====================================================

class MyFollowedOrganizationsAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        follows = (
            OrganizationFollow.objects
            .filter(
                user=request.user
            )
            .select_related(
                "organization"
            )
            .order_by(
                "-created_at"
            )
        )

        serializer = OrganizationFollowSerializer(
            follows,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )   
        
        
# =====================================================
# NOTIFICATION LIST API
# =====================================================

class NotificationListAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        notifications = (
            Notification.objects
            .filter(
                user=request.user
            )
            .select_related(
                "sender",
                "post",
                "opportunity",
                "conversation",
            )
            .order_by(
                "-created_at"
            )
        )

        serializer = NotificationSerializer(
            notifications,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
        
        
# =====================================================
# UNREAD NOTIFICATIONS API
# =====================================================

class UnreadNotificationsAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        notifications = (
            Notification.objects
            .filter(
                user=request.user,
                is_read=False
            )
            .select_related(
                "sender",
                "post",
                "opportunity",
                "conversation",
            )
            .order_by(
                "-created_at"
            )
        )

        serializer = NotificationSerializer(
            notifications,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
        
# =====================================================
# NOTIFICATION DETAIL API
# =====================================================

class NotificationDetailAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, notification_id):

        try:

            notification = (
                Notification.objects
                .select_related(
                    "sender",
                    "post",
                    "opportunity",
                    "conversation",
                )
                .get(
                    id=notification_id,
                    user=request.user
                )
            )

        except Notification.DoesNotExist:

            return Response(
                {
                    "detail": "Notification not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = NotificationSerializer(
            notification
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
        
# =====================================================
# MARK NOTIFICATION AS READ
# =====================================================

class NotificationReadAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, notification_id):

        try:

            notification = Notification.objects.get(
                id=notification_id,
                user=request.user
            )

        except Notification.DoesNotExist:

            return Response(
                {
                    "detail": "Notification not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        notification.is_read = True
        notification.save(
            update_fields=["is_read"]
        )

        serializer = NotificationSerializer(
            notification
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
# =====================================================
# MARK ALL NOTIFICATIONS AS READ
# =====================================================

class NotificationReadAllAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        updated = (
            Notification.objects
            .filter(
                user=request.user,
                is_read=False
            )
            .update(
                is_read=True
            )
        )

        return Response(
            {
                "detail": (
                    "All notifications marked as read."
                ),
                "updated_count": updated,
            },
            status=status.HTTP_200_OK
        )
        
        
        
# =====================================================
# NOTIFICATION COUNT API
# =====================================================

class NotificationCountAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        unread_count = Notification.objects.filter(
            user=request.user,
            is_read=False
        ).count()

        return Response(
            {
                "unread_count": unread_count
            },
            status=status.HTTP_200_OK
        )       
        
# =====================================================
# SHORTLIST CREATE API
# =====================================================

class ShortlistCreateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        # ---------------------------------------------
        # Organization access
        # ---------------------------------------------

        if request.user.role != "ORGANIZATION":

            return Response(
                {
                    "detail": (
                        "Only organization users can "
                        "create shortlists."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # ---------------------------------------------
        # Get organization profile
        # ---------------------------------------------

        try:

            organization = request.user.organization_profile

        except Organization.DoesNotExist:

            return Response(
                {
                    "detail": (
                        "You do not have an organization profile."
                    )
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # Get talent
        # ---------------------------------------------

        talent_id = request.data.get("talent")

        if not talent_id:

            return Response(
                {
                    "detail": "Talent is required."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        try:

            talent = TalentProfile.objects.get(
                id=talent_id
            )

        except TalentProfile.DoesNotExist:

            return Response(
                {
                    "detail": "Talent not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # Check existing shortlist
        # ---------------------------------------------

        if Shortlist.objects.filter(
            organization=organization,
            talent=talent
        ).exists():

            return Response(
                {
                    "detail": (
                        "This talent is already "
                        "on your shortlist."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------
        # Create shortlist
        # ---------------------------------------------

        shortlist = Shortlist.objects.create(
            organization=organization,
            talent=talent,
            notes=request.data.get(
                "notes",
                ""
            ),
            starred=request.data.get(
                "starred",
                False
            )
        )

        serializer = ShortlistSerializer(
            shortlist
        )

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED
        )
        
        
# =====================================================
# MY SHORTLISTS API
# =====================================================

class MyShortlistsAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        if request.user.role != "ORGANIZATION":

            return Response(
                {
                    "detail": (
                        "Only organization users can "
                        "view shortlists."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        try:

            organization = request.user.organization_profile

        except Organization.DoesNotExist:

            return Response(
                {
                    "detail": (
                        "You do not have an organization profile."
                    )
                },
                status=status.HTTP_404_NOT_FOUND
            )

        shortlists = (
            Shortlist.objects
            .filter(
                organization=organization
            )
            .select_related(
                "organization",
                "talent",
                "talent__user"
            )
            .order_by(
                "-created_at"
            )
        )

        serializer = ShortlistSerializer(
            shortlists,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
        
        
# =====================================================
# SHORTLIST DETAIL API
# =====================================================

class ShortlistDetailAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, shortlist_id):

        if request.user.role != "ORGANIZATION":

            return Response(
                {
                    "detail": (
                        "Only organization users can "
                        "view shortlists."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        try:

            organization = request.user.organization_profile

        except Organization.DoesNotExist:

            return Response(
                {
                    "detail": (
                        "You do not have an organization profile."
                    )
                },
                status=status.HTTP_404_NOT_FOUND
            )

        try:

            shortlist = (
                Shortlist.objects
                .select_related(
                    "organization",
                    "talent",
                    "talent__user"
                )
                .get(
                    id=shortlist_id,
                    organization=organization
                )
            )

        except Shortlist.DoesNotExist:

            return Response(
                {
                    "detail": "Shortlist not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = ShortlistSerializer(
            shortlist
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
        
# =====================================================
# SHORTLIST UPDATE API
# =====================================================

class ShortlistUpdateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def patch(self, request, shortlist_id):

        if request.user.role != "ORGANIZATION":

            return Response(
                {
                    "detail": (
                        "Only organization users can "
                        "update shortlists."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        try:

            organization = request.user.organization_profile

        except Organization.DoesNotExist:

            return Response(
                {
                    "detail": (
                        "You do not have an organization profile."
                    )
                },
                status=status.HTTP_404_NOT_FOUND
            )

        try:

            shortlist = Shortlist.objects.get(
                id=shortlist_id,
                organization=organization
            )

        except Shortlist.DoesNotExist:

            return Response(
                {
                    "detail": "Shortlist not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # Only allow these fields
        # ---------------------------------------------

        if "notes" in request.data:

            shortlist.notes = request.data["notes"]

        if "starred" in request.data:

            shortlist.starred = request.data["starred"]

        shortlist.save()

        serializer = ShortlistSerializer(
            shortlist
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )        
        
        
# =====================================================
# SHORTLIST DELETE API
# =====================================================

class ShortlistDeleteAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def delete(self, request, shortlist_id):

        if request.user.role != "ORGANIZATION":

            return Response(
                {
                    "detail": (
                        "Only organization users can "
                        "remove shortlists."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        try:

            organization = request.user.organization_profile

        except Organization.DoesNotExist:

            return Response(
                {
                    "detail": (
                        "You do not have an organization profile."
                    )
                },
                status=status.HTTP_404_NOT_FOUND
            )

        try:

            shortlist = Shortlist.objects.get(
                id=shortlist_id,
                organization=organization
            )

        except Shortlist.DoesNotExist:

            return Response(
                {
                    "detail": "Shortlist not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        shortlist.delete()

        return Response(
            {
                "detail": (
                    "Talent removed from shortlist."
                )
            },
            status=status.HTTP_200_OK
        )   
        
        
        
# =====================================================
# RECRUITMENT STAGE CREATE API
# =====================================================

class RecruitmentStageCreateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        # ---------------------------------------------
        # ORGANIZATION ACCESS
        # ---------------------------------------------

        if request.user.role != "ORGANIZATION":

            return Response(
                {
                    "detail": (
                        "Only organization users can "
                        "manage recruitment."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # ---------------------------------------------
        # GET ORGANIZATION
        # ---------------------------------------------

        try:

            organization = request.user.organization_profile

        except Organization.DoesNotExist:

            return Response(
                {
                    "detail": (
                        "You do not have an organization profile."
                    )
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # GET TALENT
        # ---------------------------------------------

        talent_id = request.data.get("talent")

        if not talent_id:

            return Response(
                {
                    "detail": "Talent is required."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        try:

            talent = TalentProfile.objects.get(
                id=talent_id
            )

        except TalentProfile.DoesNotExist:

            return Response(
                {
                    "detail": "Talent not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # GET OPPORTUNITY
        # ---------------------------------------------

        opportunity_id = request.data.get(
            "opportunity"
        )

        if not opportunity_id:

            return Response(
                {
                    "detail": "Opportunity is required."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        try:

            opportunity = Opportunity.objects.get(
                id=opportunity_id
            )

        except Opportunity.DoesNotExist:

            return Response(
                {
                    "detail": "Opportunity not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # VERIFY OPPORTUNITY OWNERSHIP
        # ---------------------------------------------

        if opportunity.organization != organization:

            return Response(
                {
                    "detail": (
                        "You can only manage recruitment "
                        "for your own opportunities."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # ---------------------------------------------
        # VALIDATE STAGE
        # ---------------------------------------------

        stage = request.data.get(
            "stage",
            "SHORTLISTED"
        )

        valid_stages = dict(
            RecruitmentStage.STAGES
        )

        if stage not in valid_stages:

            return Response(
                {
                    "detail": "Invalid recruitment stage.",
                    "valid_stages": list(
                        valid_stages.keys()
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------
        # CHECK DUPLICATE
        # ---------------------------------------------

        if RecruitmentStage.objects.filter(
            organization=organization,
            talent=talent,
            opportunity=opportunity
        ).exists():

            return Response(
                {
                    "detail": (
                        "This talent already exists "
                        "in this recruitment pipeline."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------
        # CREATE RECRUITMENT RECORD
        # ---------------------------------------------

        recruitment = RecruitmentStage.objects.create(
            organization=organization,
            talent=talent,
            opportunity=opportunity,
            stage=stage,
            notes=request.data.get(
                "notes",
                ""
            )
        )

        serializer = RecruitmentStageSerializer(
            recruitment
        )

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED
        )
        
        
# =====================================================
# MY RECRUITMENT PIPELINE API
# =====================================================

class MyRecruitmentPipelineAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        # ---------------------------------------------
        # ORGANIZATION ACCESS
        # ---------------------------------------------

        if request.user.role != "ORGANIZATION":

            return Response(
                {
                    "detail": (
                        "Only organization users can "
                        "view recruitment."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # ---------------------------------------------
        # GET ORGANIZATION
        # ---------------------------------------------

        try:

            organization = request.user.organization_profile

        except Organization.DoesNotExist:

            return Response(
                {
                    "detail": (
                        "You do not have an organization profile."
                    )
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # GET PIPELINE
        # ---------------------------------------------

        pipeline = (
            RecruitmentStage.objects
            .filter(
                organization=organization
            )
            .select_related(
                "organization",
                "talent",
                "talent__user",
                "opportunity",
            )
            .order_by(
                "-updated_at"
            )
        )

        serializer = RecruitmentStageSerializer(
            pipeline,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
        
# =====================================================
# RECRUITMENT DETAIL API
# =====================================================

class RecruitmentStageDetailAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, recruitment_id):

        # ---------------------------------------------
        # ORGANIZATION ACCESS
        # ---------------------------------------------

        if request.user.role != "ORGANIZATION":

            return Response(
                {
                    "detail": (
                        "Only organization users can "
                        "view recruitment."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # ---------------------------------------------
        # GET ORGANIZATION
        # ---------------------------------------------

        try:

            organization = request.user.organization_profile

        except Organization.DoesNotExist:

            return Response(
                {
                    "detail": (
                        "You do not have an organization profile."
                    )
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # GET RECRUITMENT RECORD
        # ---------------------------------------------

        try:

            recruitment = (
                RecruitmentStage.objects
                .select_related(
                    "organization",
                    "talent",
                    "talent__user",
                    "opportunity",
                )
                .get(
                    id=recruitment_id,
                    organization=organization
                )
            )

        except RecruitmentStage.DoesNotExist:

            return Response(
                {
                    "detail": "Recruitment record not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = RecruitmentStageSerializer(
            recruitment
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )                             
        
        
        
# =====================================================
# RECRUITMENT STAGE UPDATE API
# =====================================================

class RecruitmentStageUpdateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def patch(self, request, recruitment_id):

        # ---------------------------------------------
        # ORGANIZATION ACCESS
        # ---------------------------------------------

        if request.user.role != "ORGANIZATION":

            return Response(
                {
                    "detail": (
                        "Only organization users can "
                        "update recruitment."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # ---------------------------------------------
        # GET ORGANIZATION
        # ---------------------------------------------

        try:

            organization = request.user.organization_profile

        except Organization.DoesNotExist:

            return Response(
                {
                    "detail": (
                        "You do not have an organization profile."
                    )
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # GET RECRUITMENT
        # ---------------------------------------------

        try:

            recruitment = RecruitmentStage.objects.get(
                id=recruitment_id,
                organization=organization
            )

        except RecruitmentStage.DoesNotExist:

            return Response(
                {
                    "detail": "Recruitment record not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # UPDATE STAGE
        # ---------------------------------------------

        if "stage" in request.data:

            stage = request.data["stage"]

            valid_stages = dict(
                RecruitmentStage.STAGES
            )

            if stage not in valid_stages:

                return Response(
                    {
                        "detail": "Invalid recruitment stage.",
                        "valid_stages": list(
                            valid_stages.keys()
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            recruitment.stage = stage

        # ---------------------------------------------
        # UPDATE NOTES
        # ---------------------------------------------

        if "notes" in request.data:

            recruitment.notes = request.data["notes"]

        recruitment.save()

        serializer = RecruitmentStageSerializer(
            recruitment
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )        
         
         
# =====================================================
# RECRUITMENT DELETE API
# =====================================================

class RecruitmentStageDeleteAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def delete(self, request, recruitment_id):

        # ---------------------------------------------
        # ORGANIZATION ACCESS
        # ---------------------------------------------

        if request.user.role != "ORGANIZATION":

            return Response(
                {
                    "detail": (
                        "Only organization users can "
                        "delete recruitment records."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # ---------------------------------------------
        # GET ORGANIZATION
        # ---------------------------------------------

        try:

            organization = request.user.organization_profile

        except Organization.DoesNotExist:

            return Response(
                {
                    "detail": (
                        "You do not have an organization profile."
                    )
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # GET RECRUITMENT
        # ---------------------------------------------

        try:

            recruitment = RecruitmentStage.objects.get(
                id=recruitment_id,
                organization=organization
            )

        except RecruitmentStage.DoesNotExist:

            return Response(
                {
                    "detail": "Recruitment record not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # DELETE
        # ---------------------------------------------

        recruitment.delete()

        return Response(
            {
                "detail": (
                    "Recruitment record deleted successfully."
                )
            },
            status=status.HTTP_200_OK
        )                                
        



# =====================================================
# INVITATION CREATE API
# =====================================================

class InvitationCreateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        # ---------------------------------------------
        # ORGANIZATION ACCESS
        # ---------------------------------------------

        if request.user.role != "ORGANIZATION":

            return Response(
                {
                    "detail": (
                        "Only organization users can "
                        "send invitations."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # ---------------------------------------------
        # GET ORGANIZATION
        # ---------------------------------------------

        try:

            organization = request.user.organization_profile

        except Organization.DoesNotExist:

            return Response(
                {
                    "detail": (
                        "You do not have an organization profile."
                    )
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # GET TALENT
        # ---------------------------------------------

        talent_id = request.data.get("talent")

        if not talent_id:

            return Response(
                {
                    "detail": "Talent is required."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        try:

            talent = TalentProfile.objects.get(
                id=talent_id
            )

        except TalentProfile.DoesNotExist:

            return Response(
                {
                    "detail": "Talent not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # GET OPPORTUNITY
        # ---------------------------------------------

        opportunity_id = request.data.get(
            "opportunity"
        )

        if not opportunity_id:

            return Response(
                {
                    "detail": "Opportunity is required."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        try:

            opportunity = Opportunity.objects.get(
                id=opportunity_id
            )

        except Opportunity.DoesNotExist:

            return Response(
                {
                    "detail": "Opportunity not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # VERIFY OPPORTUNITY OWNERSHIP
        # ---------------------------------------------

        if opportunity.organization != organization:

            return Response(
                {
                    "detail": (
                        "You can only send invitations "
                        "for your own opportunities."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # ---------------------------------------------
        # CHECK EXISTING PENDING INVITATION
        # ---------------------------------------------

        existing_invitation = Invitation.objects.filter(
            organization=organization,
            talent=talent,
            opportunity=opportunity,
            status="PENDING"
        ).first()

        if existing_invitation:

            return Response(
                {
                    "detail": (
                        "A pending invitation already "
                        "exists for this talent."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------
        # CREATE INVITATION
        # ---------------------------------------------

        invitation = Invitation.objects.create(
            organization=organization,
            talent=talent,
            opportunity=opportunity,
            message=request.data.get(
                "message",
                ""
            )
        )

        # ---------------------------------------------
        # UPDATE RECRUITMENT PIPELINE
        # ---------------------------------------------

        recruitment, created = (
            RecruitmentStage.objects.get_or_create(
                organization=organization,
                talent=talent,
                opportunity=opportunity,
                defaults={
                    "stage": "INVITED"
                }
            )
        )

        if not created:

            recruitment.stage = "INVITED"
            recruitment.save()

        # ---------------------------------------------
        # SERIALIZE
        # ---------------------------------------------

        serializer = InvitationSerializer(
            invitation
        )

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED
        )
        
        
# =====================================================
# RECEIVED INVITATIONS API
# =====================================================

class ReceivedInvitationsAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        # ---------------------------------------------
        # GET TALENT PROFILE
        # ---------------------------------------------

        try:

            talent = request.user.talent_profile

        except TalentProfile.DoesNotExist:

            return Response(
                {
                    "detail": (
                        "You do not have a talent profile."
                    )
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # GET INVITATIONS
        # ---------------------------------------------

        invitations = (
            Invitation.objects
            .filter(
                talent=talent
            )
            .select_related(
                "organization",
                "talent",
                "talent__user",
                "opportunity",
            )
            .order_by(
                "-created_at"
            )
        )

        serializer = InvitationSerializer(
            invitations,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
        
        
# =====================================================
# SENT INVITATIONS API
# =====================================================

class SentInvitationsAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        if request.user.role != "ORGANIZATION":

            return Response(
                {
                    "detail": (
                        "Only organization users can "
                        "view sent invitations."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        try:

            organization = request.user.organization_profile

        except Organization.DoesNotExist:

            return Response(
                {
                    "detail": (
                        "You do not have an organization profile."
                    )
                },
                status=status.HTTP_404_NOT_FOUND
            )

        invitations = (
            Invitation.objects
            .filter(
                organization=organization
            )
            .select_related(
                "organization",
                "talent",
                "talent__user",
                "opportunity",
            )
            .order_by(
                "-created_at"
            )
        )

        serializer = InvitationSerializer(
            invitations,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
        
        
# =====================================================
# INVITATION RESPONSE API
# =====================================================

class InvitationRespondAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def patch(self, request, invitation_id):

        # ---------------------------------------------
        # GET TALENT
        # ---------------------------------------------

        try:

            talent = request.user.talent_profile

        except TalentProfile.DoesNotExist:

            return Response(
                {
                    "detail": (
                        "You do not have a talent profile."
                    )
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # GET INVITATION
        # ---------------------------------------------

        try:

            invitation = (
                Invitation.objects
                .select_related(
                    "organization",
                    "talent",
                    "opportunity",
                )
                .get(
                    id=invitation_id,
                    talent=talent
                )
            )

        except Invitation.DoesNotExist:

            return Response(
                {
                    "detail": "Invitation not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # CHECK CURRENT STATUS
        # ---------------------------------------------

        if invitation.status != "PENDING":

            return Response(
                {
                    "detail": (
                        "This invitation has already "
                        "been responded to."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------
        # GET RESPONSE
        # ---------------------------------------------

        response_status = request.data.get(
            "status"
        )

        if response_status not in [
            "ACCEPTED",
            "DECLINED"
        ]:

            return Response(
                {
                    "detail": (
                        "Status must be ACCEPTED "
                        "or DECLINED."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------
        # ACCEPT
        # ---------------------------------------------

        if response_status == "ACCEPTED":

            invitation.accept()

            # Update recruitment pipeline
            recruitment, created = (
                RecruitmentStage.objects.get_or_create(
                    organization=invitation.organization,
                    talent=invitation.talent,
                    opportunity=invitation.opportunity,
                    defaults={
                        "stage": "INVITED"
                    }
                )
            )

            if not created:

                recruitment.stage = "INVITED"
                recruitment.save()

        # ---------------------------------------------
        # DECLINE
        # ---------------------------------------------

        else:

            invitation.decline()

            recruitment = (
                RecruitmentStage.objects.filter(
                    organization=invitation.organization,
                    talent=invitation.talent,
                    opportunity=invitation.opportunity
                ).first()
            )

            if recruitment:

                recruitment.stage = "REJECTED"
                recruitment.save()

        # ---------------------------------------------
        # RESPONSE
        # ---------------------------------------------

        serializer = InvitationSerializer(
            invitation
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
        
        
        
# =====================================================
# INVITATION DETAIL API
# =====================================================

class InvitationDetailAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, invitation_id):

        try:

            invitation = (
                Invitation.objects
                .select_related(
                    "organization",
                    "talent",
                    "talent__user",
                    "opportunity",
                )
                .get(
                    id=invitation_id
                )
            )

        except Invitation.DoesNotExist:

            return Response(
                {
                    "detail": "Invitation not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # ACCESS CONTROL
        # ---------------------------------------------

        is_talent = False
        is_organization = False

        try:

            is_talent = (
                invitation.talent.user ==
                request.user
            )

        except Exception:

            pass

        try:

            is_organization = (
                invitation.organization ==
                request.user.organization_profile
            )

        except Exception:

            pass

        if not is_talent and not is_organization:

            return Response(
                {
                    "detail": "You do not have access to this invitation."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = InvitationSerializer(
            invitation
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
 
# =====================================================
# SEND CONNECTION REQUEST API
# =====================================================

class ConnectionSendAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        receiver_id = request.data.get("receiver")

        if not receiver_id:

            return Response(
                {
                    "detail": "Receiver is required."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------
        # GET RECEIVER
        # ---------------------------------------------

        try:

            receiver = User.objects.get(
                id=receiver_id
            )

        except User.DoesNotExist:

            return Response(
                {
                    "detail": "User not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # PREVENT SELF-CONNECTION
        # ---------------------------------------------

        if receiver == request.user:

            return Response(
                {
                    "detail": (
                        "You cannot send a connection "
                        "request to yourself."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------
        # CHECK EXISTING REQUEST
        # ---------------------------------------------

        existing = Connection.objects.filter(
            sender=request.user,
            receiver=receiver
        ).first()

        if existing:

            return Response(
                {
                    "detail": (
                        "A connection request already exists."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------
        # CHECK REVERSE REQUEST
        # ---------------------------------------------

        reverse_request = Connection.objects.filter(
            sender=receiver,
            receiver=request.user
        ).first()

        if reverse_request:

            if reverse_request.status == "PENDING":

                return Response(
                    {
                        "detail": (
                            "This user has already sent "
                            "you a connection request."
                        ),
                        "connection_id": reverse_request.id
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

        # ---------------------------------------------
        # CREATE REQUEST
        # ---------------------------------------------

        connection = Connection.objects.create(
            sender=request.user,
            receiver=receiver
        )

        # ---------------------------------------------
        # CREATE NOTIFICATION
        # ---------------------------------------------

        Notification.objects.create(
            user=receiver,
            sender=request.user,
            notification_type="CONNECTION",
            message=(
                f"{request.user.get_full_name() or request.user.username} "
                "sent you a connection request."
            )
        )

        serializer = ConnectionSerializer(
            connection
        )

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED
        )


# =====================================================
# MY CONNECTIONS API
# =====================================================

class MyConnectionsAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        connections = (
            Connection.objects
            .filter(
                models.Q(
                    sender=request.user,
                    status="ACCEPTED"
                )
                |
                models.Q(
                    receiver=request.user,
                    status="ACCEPTED"
                )
            )
            .select_related(
                "sender",
                "receiver"
            )
            .order_by(
                "-updated_at"
            )
        )

        serializer = ConnectionSerializer(
            connections,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
        
# =====================================================
# RECEIVED CONNECTION REQUESTS API
# =====================================================

class ReceivedConnectionsAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        connections = (
            Connection.objects
            .filter(
                receiver=request.user,
                status="PENDING"
            )
            .select_related(
                "sender",
                "receiver"
            )
            .order_by(
                "-created_at"
            )
        )

        serializer = ConnectionSerializer(
            connections,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
        
        
# =====================================================
# SENT CONNECTION REQUESTS API
# =====================================================

class SentConnectionsAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        connections = (
            Connection.objects
            .filter(
                sender=request.user
            )
            .select_related(
                "sender",
                "receiver"
            )
            .order_by(
                "-created_at"
            )
        )

        serializer = ConnectionSerializer(
            connections,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
        
# =====================================================
# CONNECTION RESPONSE API
# =====================================================

class ConnectionRespondAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def patch(self, request, connection_id):

        # ---------------------------------------------
        # GET CONNECTION
        # ---------------------------------------------

        try:

            connection = (
                Connection.objects
                .select_related(
                    "sender",
                    "receiver"
                )
                .get(
                    id=connection_id
                )
            )

        except Connection.DoesNotExist:

            return Response(
                {
                    "detail": "Connection request not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # ONLY RECEIVER CAN RESPOND
        # ---------------------------------------------

        if connection.receiver != request.user:

            return Response(
                {
                    "detail": (
                        "Only the receiver can respond "
                        "to this connection request."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # ---------------------------------------------
        # MUST BE PENDING
        # ---------------------------------------------

        if connection.status != "PENDING":

            return Response(
                {
                    "detail": (
                        "This connection request has "
                        "already been processed."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------
        # GET RESPONSE
        # ---------------------------------------------

        new_status = request.data.get(
            "status"
        )

        if new_status not in [
            "ACCEPTED",
            "REJECTED"
        ]:

            return Response(
                {
                    "detail": (
                        "Status must be ACCEPTED "
                        "or REJECTED."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------
        # UPDATE
        # ---------------------------------------------

        connection.status = new_status
        connection.save()

        # ---------------------------------------------
        # ACCEPTED NOTIFICATION
        # ---------------------------------------------

        if new_status == "ACCEPTED":

            Notification.objects.create(
                user=connection.sender,
                sender=request.user,
                notification_type="CONNECTION",
                message=(
                    f"{request.user.get_full_name() or request.user.username} "
                    "accepted your connection request."
                )
            )

        # ---------------------------------------------
        # REJECTED NOTIFICATION
        # ---------------------------------------------

        else:

            Notification.objects.create(
                user=connection.sender,
                sender=request.user,
                notification_type="CONNECTION",
                message=(
                    f"{request.user.get_full_name() or request.user.username} "
                    "rejected your connection request."
                )
            )

        serializer = ConnectionSerializer(
            connection
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
        
# =====================================================
# CONNECTION DETAIL API
# =====================================================

class ConnectionDetailAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, connection_id):

        try:

            connection = (
                Connection.objects
                .select_related(
                    "sender",
                    "receiver"
                )
                .get(
                    id=connection_id
                )
            )

        except Connection.DoesNotExist:

            return Response(
                {
                    "detail": "Connection not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # ACCESS CONTROL
        # ---------------------------------------------

        if (
            connection.sender != request.user
            and
            connection.receiver != request.user
        ):

            return Response(
                {
                    "detail": (
                        "You do not have access "
                        "to this connection."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = ConnectionSerializer(
            connection
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )  
        
        
# =====================================================
# ROLE MODEL ADMIN API
# =====================================================


class RoleModelAssignmentListAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        if request.user.role != "ADMIN":

            return Response(
                {
                    "detail":
                    "Only ADMIN users can access Role Model management."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        assignments = (
            RoleModelAssignment.objects
            .select_related(
                "talent__user",
                "assigned_by",
                "reviewed_by",
            )
        )

        serializer = RoleModelAssignmentSerializer(
            assignments,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
        
class RoleModelManualAssignmentAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        if request.user.role != "ADMIN":

            return Response(
                {
                    "detail":
                    "Only ADMIN users can manually assign Role Models."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        talent_id = request.data.get("talent")
        category = request.data.get("category", "")
        reason = request.data.get("reason", "")

        if not talent_id:

            return Response(
                {
                    "detail":
                    "The talent field is required."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        try:

            talent = TalentProfile.objects.get(
                id=talent_id
            )

        except TalentProfile.DoesNotExist:

            return Response(
                {
                    "detail":
                    "Talent profile not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        try:

            assignment = (
                FollowerAnalyticsService
                .create_manual_role_model_assignment(
                    talent=talent,
                    assigned_by=request.user,
                    category=category,
                    reason=reason,
                )
            )

        except ValueError as error:

            return Response(
                {
                    "detail": str(error)
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        except PermissionError as error:

            return Response(
                {
                    "detail": str(error)
                },
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = RoleModelAssignmentSerializer(
            assignment
        )

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED
        ) 
        
        
        
# =====================================================
# ROLE MODEL RECOMMENDATIONS API
# =====================================================

class RoleModelRecommendationAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        if request.user.role != "ATHLETE":

            return Response(
                {
                    "detail": (
                        "Only talents can access role model "
                        "recommendations."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        try:

            talent = request.user.talent_profile

        except TalentProfile.DoesNotExist:

            return Response(
                {
                    "detail": "You do not have a talent profile."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        recommendations = (
            RecommendationEngine
            .recommend_role_models_for_talent(
                talent
            )
        )

        results = []

        for recommendation in recommendations:

            role_model = recommendation["role_model"]

            results.append(
                {
                    "role_model_id": role_model.id,

                    "role_model_name": (
                        role_model.user.get_full_name()
                        or role_model.user.username
                    ),

                    "role_model_username": (
                        role_model.user.username
                    ),

                    "score": float(
                        recommendation["score"]
                    ),

                    "reasons": (
                        recommendation["reasons"]
                    ),
                }
            )

        serializer = RoleModelRecommendationSerializer(
            results,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )


# =====================================================
# COURSE RECOMMENDATIONS API
# =====================================================

class CourseRecommendationAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        if request.user.role != "ATHLETE":

            return Response(
                {
                    "detail": (
                        "Only talents can access "
                        "course recommendations."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        try:

            talent = request.user.talent_profile

        except TalentProfile.DoesNotExist:

            return Response(
                {
                    "detail": "You do not have a talent profile."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        engine = RecommendationEngine()

        recommendations = (
            engine.recommend_courses_for_talent(
                talent
            )
        )

        results = []

        for recommendation in recommendations:

            course = recommendation["course"]

            results.append(
                {
                    "course_id": course.id,

                    "course_title": (
                        course.title
                    ),

                    "score": float(
                        recommendation["score"]
                    ),

                    "reasons": [
                        recommendation["reason"]
                    ],
                }
            )

        serializer = CourseRecommendationSerializer(
            results,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )


# =====================================================
# EVENT RECOMMENDATIONS API
# =====================================================

class EventRecommendationAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        if request.user.role != "ATHLETE":

            return Response(
                {
                    "detail": (
                        "Only talents can access "
                        "event recommendations."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        try:

            talent = request.user.talent_profile

        except TalentProfile.DoesNotExist:

            return Response(
                {
                    "detail": "You do not have a talent profile."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        engine = RecommendationEngine()

        recommendations = (
            engine.recommend_events_for_talent(
                talent
            )
        )

        results = []

        for recommendation in recommendations:

            event = recommendation["event"]

            results.append(
                {
                    "event_id": event.id,

                    "event_title": (
                        event.title
                    ),

                    "score": float(
                        recommendation["score"]
                    ),

                    "reasons": [
                        recommendation["reason"]
                    ],
                }
            )

        serializer = EventRecommendationSerializer(
            results,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )                                                                                                                                                                                                                                                                                                                                                                                                                                 
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from applications.models import Application
from shortlists.models import Shortlist
from accounts.models import User
from recruitment.models import RecruitmentStage
from invitations.models import Invitation
from connections.models import Connection
from notifications.models import Notification
from talents.models import RoleModelAssignment
from connections.models import (
    Connection,
    Follow,
    OrganizationFollow,
)
from analytics.models import (
    TalentScore,
    TalentProfileView,
    RecommendationHistory,
)

from talents.models import (
    TalentProfile,
    Achievement,
    Certification,
    Experience,
)

from organizations.models import (
    Organization,
    OrganizationCategory,
    OrganizationDomain,
    SportsOrganizationProfile,
)

from opportunities.models import (
    Opportunity,
    OpportunityRequirement,
)


# =====================================================
# USER SERIALIZER
# =====================================================

class UserSerializer(serializers.ModelSerializer):

    class Meta:

        model = User

        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "role",
            "profile_picture",
            "country",
        ]

        read_only_fields = [
            "id",
            "role",
        ]


# =====================================================
# ACHIEVEMENT SERIALIZER
# =====================================================

class AchievementSerializer(serializers.ModelSerializer):

    class Meta:

        model = Achievement

        fields = [
            "id",
            "title",
            "description",
            "date_received",
            "image",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "created_at",
        ]


# =====================================================
# CERTIFICATION SERIALIZER
# =====================================================

class CertificationSerializer(serializers.ModelSerializer):

    class Meta:

        model = Certification

        fields = [
            "id",
            "name",
            "issuing_organization",
            "issue_date",
            "certificate_file",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "created_at",
        ]


# =====================================================
# EXPERIENCE SERIALIZER
# =====================================================

class ExperienceSerializer(serializers.ModelSerializer):

    class Meta:

        model = Experience

        fields = [
            "id",
            "company",
            "role",
            "description",
            "start_date",
            "end_date",
            "currently_working",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "created_at",
        ]


# =====================================================
# TALENT PROFILE SERIALIZER
# =====================================================

class TalentProfileSerializer(serializers.ModelSerializer):

    user = UserSerializer(
        read_only=True
    )

    domains = serializers.StringRelatedField(
        many=True,
        read_only=True
    )

    skills = serializers.StringRelatedField(
        many=True,
        read_only=True
    )

    achievements = AchievementSerializer(
        many=True,
        read_only=True
    )

    certifications = CertificationSerializer(
        many=True,
        read_only=True
    )

    experiences = ExperienceSerializer(
        many=True,
        read_only=True
    )

    class Meta:

        model = TalentProfile

        fields = [

            "id",

            # User
            "user",

            # Basic profile
            "headline",
            "biography",

            # Location
            "country",
            "city",
            
            # Classification
            "talent_category",
            "profile_visibility",

            # Professional
            "experience_level",
            "preferred_work_type",
            "availability_status",

            # Skills / domains
            "domains",
            "skills",

            # Media
            "profile_photo",
            "cover_photo",

            # Verification
            "verified",

            # Role model
            "is_role_model",
            "role_model_category",

            # Social
            "followers_count",

            # Related information
            "achievements",
            "certifications",
            "experiences",

            # Metadata
            "created_at",
        ]

        read_only_fields = [

            "id",
            "user",
            "verified",
            "followers_count",
            "created_at",

        ]


# =====================================================
# ORGANIZATION CATEGORY SERIALIZER
# =====================================================

class OrganizationCategorySerializer(serializers.ModelSerializer):

    class Meta:

        model = OrganizationCategory

        fields = [
            "id",
            "name",
            "description",
        ]

        read_only_fields = [
            "id",
        ]


# =====================================================
# ORGANIZATION DOMAIN SERIALIZER
# =====================================================

class OrganizationDomainSerializer(serializers.ModelSerializer):

    category_name = serializers.CharField(
        source="category.name",
        read_only=True
    )

    class Meta:

        model = OrganizationDomain

        fields = [
            "id",
            "name",
            "description",
            "category",
            "category_name",
        ]

        read_only_fields = [
            "id",
            "category_name",
        ]


# =====================================================
# SPORTS ORGANIZATION PROFILE SERIALIZER
# =====================================================

class SportsOrganizationProfileSerializer(
    serializers.ModelSerializer
):

    sport_name = serializers.CharField(
        source="sport.name",
        read_only=True
    )

    class Meta:

        model = SportsOrganizationProfile

        fields = [
            "id",
            "sport",
            "sport_name",
            "league",
            "level",
            "founded",
            "stadium",
            "nickname",
            "colors",
            "website",
        ]

        read_only_fields = [
            "id",
            "sport_name",
        ]


# =====================================================
# ORGANIZATION SERIALIZER
# =====================================================

class OrganizationSerializer(serializers.ModelSerializer):

    category_name = serializers.CharField(
        source="category.name",
        read_only=True
    )

    domain_name = serializers.CharField(
        source="domain.name",
        read_only=True
    )

    followers_count = serializers.IntegerField(
        source="followers.count",
        read_only=True
    )

    sports_profile = SportsOrganizationProfileSerializer(
        read_only=True
    )

    class Meta:

        model = Organization

        fields = [
            "id",
            "name",

            # Classification
            "category",
            "category_name",
            "domain",
            "domain_name",

            # Location
            "country",
            "city",
            "headquarters",

            # Contact
            "website",
            "email",
            "phone",

            # Description
            "description",

            # Media
            "logo",
            "cover_photo",

            # Organization information
            "founded_year",
            "organization_size",
            "level",

            # Verification / status
            "official",
            "claimed",
            "claimed_at",
            "verified",
            "status",

            # Social
            "followers_count",

            # Sports
            "sports_profile",

            # Metadata
            "created_at",
        ]

        read_only_fields = [
            "id",
            "category_name",
            "domain_name",
            "followers_count",
            "sports_profile",
            "claimed_at",
            "created_at",
        ]
        
        
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
# OPPORTUNITY REQUIREMENT SERIALIZER
# =====================================================

class OpportunityRequirementSerializer(
    serializers.ModelSerializer
):

    skill_name = serializers.CharField(
        source="skill.name",
        read_only=True
    )

    class Meta:

        model = OpportunityRequirement

        fields = [
            "id",
            "skill",
            "skill_name",
            "importance",
        ]

        read_only_fields = [
            "id",
            "skill_name",
        ]


# =====================================================
# OPPORTUNITY SERIALIZER
# =====================================================

class OpportunitySerializer(
    serializers.ModelSerializer
):

    organization_name = serializers.CharField(
        source="organization.name",
        read_only=True
    )

    domain_name = serializers.CharField(
        source="domain.name",
        read_only=True
    )

    skills = serializers.StringRelatedField(
        many=True,
        read_only=True
    )

    requirements = OpportunityRequirementSerializer(
        many=True,
        read_only=True
    )

    class Meta:

        model = Opportunity

        fields = [
            "id",

            # Organization
            "organization",
            "organization_name",

            # Basic information
            "title",
            "description",
            "opportunity_type",

            # Professional requirements
            "domain",
            "domain_name",
            "skills",
            "experience_level",

            # Work information
            "work_type",
            "location",

            # Application information
            "deadline",
            "active",

            # Requirements
            "requirements",

            # Metadata
            "created_at",
        ]

        read_only_fields = [
            "id",
            "organization_name",
            "domain_name",
            "skills",
            "requirements",
            "created_at",
        ]
        


# =====================================================
# OPPORTUNITY CREATE SERIALIZER
# =====================================================

class OpportunityCreateSerializer(
    serializers.ModelSerializer
):

    class Meta:

        model = Opportunity

        fields = [
            "title",
            "description",
            "opportunity_type",
            "domain",
            "skills",
            "experience_level",
            "work_type",
            "location",
            "deadline",
            "active",
        ]

        read_only_fields = [
            "active",
        ]

    def create(self, validated_data):

        skills = validated_data.pop(
            "skills",
            []
        )

        opportunity = Opportunity.objects.create(
            **validated_data
        )

        opportunity.skills.set(
            skills
        )

        return opportunity     
    
    
    
# =====================================================
# APPLICATION SERIALIZER
# =====================================================

class ApplicationSerializer(
    serializers.ModelSerializer
):

    talent_name = serializers.CharField(
        source="talent.user.get_full_name",
        read_only=True
    )

    opportunity_title = serializers.CharField(
        source="opportunity.title",
        read_only=True
    )

    organization_name = serializers.CharField(
        source="opportunity.organization.name",
        read_only=True
    )

    class Meta:

        model = Application

        fields = [
            "id",

            # Talent
            "talent",
            "talent_name",

            # Opportunity
            "opportunity",
            "opportunity_title",

            # Organization
            "organization_name",

            # Application
            "message",
            "status",

            # Metadata
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "talent",
            "talent_name",
            "opportunity_title",
            "organization_name",
            "status",
            "created_at",
            "updated_at",
        ]


# =====================================================
# APPLICATION CREATE SERIALIZER
# =====================================================

class ApplicationCreateSerializer(
    serializers.ModelSerializer
):

    class Meta:

        model = Application

        fields = [
            "opportunity",
            "message",
        ]

        read_only_fields = [
            "opportunity",
        ]               
        
        
# =====================================================
# APPLICATION LIST API
# =====================================================

class ApplicationListAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        # ---------------------------------------------
        # TALENT
        # ---------------------------------------------

        if request.user.role == "ATHLETE":

            try:

                talent = request.user.talent_profile

            except TalentProfile.DoesNotExist:

                return Response(
                    {
                        "detail":
                        "You do not have a talent profile."
                    },
                    status=status.HTTP_404_NOT_FOUND
                )

            applications = (
                Application.objects
                .select_related(
                    "talent",
                    "talent__user",
                    "opportunity",
                    "opportunity__organization",
                )
                .filter(
                    talent=talent
                )
                .order_by(
                    "-created_at"
                )
            )

        # ---------------------------------------------
        # ORGANIZATION
        # ---------------------------------------------

        elif request.user.role == "ORGANIZATION":

            try:

                organization = request.user.organization_profile

            except Organization.DoesNotExist:

                return Response(
                    {
                        "detail":
                        "You do not have an organization profile."
                    },
                    status=status.HTTP_404_NOT_FOUND
                )

            applications = (
                Application.objects
                .select_related(
                    "talent",
                    "talent__user",
                    "opportunity",
                    "opportunity__organization",
                )
                .filter(
                    opportunity__organization=organization
                )
                .order_by(
                    "-created_at"
                )
            )

        else:

            return Response(
                {
                    "detail":
                    "You do not have permission to view applications."
                },
                status=status.HTTP_403_FORBIDDEN
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
# CREATE APPLICATION API
# =====================================================

class ApplicationCreateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        # ---------------------------------------------
        # TALENT CHECK
        # ---------------------------------------------

        if request.user.role != "ATHLETE":

            return Response(
                {
                    "detail":
                    "Only talent accounts can apply for opportunities."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # ---------------------------------------------
        # TALENT PROFILE
        # ---------------------------------------------

        try:

            talent = request.user.talent_profile

        except TalentProfile.DoesNotExist:

            return Response(
                {
                    "detail":
                    "You do not have a talent profile."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # VALIDATE DATA
        # ---------------------------------------------

        serializer = ApplicationCreateSerializer(
            data=request.data
        )

        if not serializer.is_valid():

            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        opportunity = serializer.validated_data[
            "opportunity"
        ]

        # ---------------------------------------------
        # OPPORTUNITY CHECK
        # ---------------------------------------------

        if not opportunity.active:

            return Response(
                {
                    "detail":
                    "This opportunity is no longer active."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------
        # DEADLINE CHECK
        # ---------------------------------------------

        from django.utils import timezone

        if (
            opportunity.deadline
            and opportunity.deadline < timezone.localdate()
        ):

            return Response(
                {
                    "detail":
                    "The application deadline has passed."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------
        # DUPLICATE APPLICATION CHECK
        # ---------------------------------------------

        if Application.objects.filter(
            talent=talent,
            opportunity=opportunity
        ).exists():

            return Response(
                {
                    "detail":
                    "You have already applied for this opportunity."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------
        # CREATE APPLICATION
        # ---------------------------------------------

        application = serializer.save(
            talent=talent
        )

        # ---------------------------------------------
        # RETURN APPLICATION
        # ---------------------------------------------

        response_serializer = ApplicationSerializer(
            application
        )

        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED
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
                )
                .get(
                    id=application_id
                )
            )

        except Application.DoesNotExist:

            return Response(
                {
                    "detail":
                    "Application not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # ACCESS CONTROL
        # ---------------------------------------------

        is_talent = (
            request.user.role == "ATHLETE"
            and application.talent.user_id == request.user.id
        )

        is_organization = (
            request.user.role == "ORGANIZATION"
            and application.opportunity.organization.user_id
            == request.user.id
        )

        if not (is_talent or is_organization):

            return Response(
                {
                    "detail":
                    "You do not have permission to view this application."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = ApplicationSerializer(
            application
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )                        
        
        
        
# =====================================================
# SHORTLIST SERIALIZERS
# =====================================================

class ShortlistSerializer(serializers.ModelSerializer):

    organization_id = serializers.IntegerField(
        source="organization.id",
        read_only=True
    )

    organization_name = serializers.CharField(
        source="organization.name",
        read_only=True
    )

    talent_id = serializers.IntegerField(
        source="talent.id",
        read_only=True
    )

    talent_name = serializers.CharField(
        source="talent.user.get_full_name",
        read_only=True
    )

    talent_username = serializers.CharField(
        source="talent.user.username",
        read_only=True
    )

    class Meta:

        model = Shortlist

        fields = [
            "id",

            # Organization
            "organization_id",
            "organization_name",

            # Talent
            "talent_id",
            "talent_name",
            "talent_username",

            # Shortlist
            "notes",
            "starred",

            # Metadata
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "organization_id",
            "organization_name",
            "talent_id",
            "talent_name",
            "talent_username",
            "created_at",
            "updated_at",
        ]


class ShortlistCreateSerializer(serializers.ModelSerializer):

    class Meta:

        model = Shortlist

        fields = [
            "talent",
            "notes",
            "starred",
        ]        
        
        
        
# =====================================================
# RECRUITMENT PIPELINE SERIALIZERS
# =====================================================

class RecruitmentStageSerializer(serializers.ModelSerializer):

    organization_id = serializers.IntegerField(
        source="organization.id",
        read_only=True
    )

    organization_name = serializers.CharField(
        source="organization.name",
        read_only=True
    )

    talent_id = serializers.IntegerField(
        source="talent.id",
        read_only=True
    )

    talent_name = serializers.CharField(
        source="talent.user.get_full_name",
        read_only=True
    )

    talent_username = serializers.CharField(
        source="talent.user.username",
        read_only=True
    )

    opportunity_id = serializers.IntegerField(
        source="opportunity.id",
        read_only=True
    )

    opportunity_title = serializers.CharField(
        source="opportunity.title",
        read_only=True
    )

    class Meta:

        model = RecruitmentStage

        fields = [
            "id",

            # Organization
            "organization_id",
            "organization_name",

            # Talent
            "talent_id",
            "talent_name",
            "talent_username",

            # Opportunity
            "opportunity_id",
            "opportunity_title",

            # Pipeline
            "stage",
            "notes",

            # Metadata
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "organization_id",
            "organization_name",
            "talent_id",
            "talent_name",
            "talent_username",
            "opportunity_id",
            "opportunity_title",
            "created_at",
            "updated_at",
        ]


class RecruitmentStageCreateSerializer(serializers.ModelSerializer):

    class Meta:

        model = RecruitmentStage

        fields = [
            "talent",
            "opportunity",
            "stage",
            "notes",
        ]

        extra_kwargs = {
            "stage": {
                "required": False
            }
        } 
        
        
# =====================================================
# RECOMMENDATION SERIALIZER
# =====================================================

class RecommendationSerializer(serializers.Serializer):

    talent_id = serializers.IntegerField()

    talent_name = serializers.CharField()

    talent_username = serializers.CharField()

    score = serializers.FloatField()

    reasons = serializers.ListField(
        child=serializers.CharField()
    )  
    
# =====================================================
# TALENT SCORE SERIALIZER
# =====================================================

class TalentScoreSerializer(serializers.ModelSerializer):

    talent_id = serializers.IntegerField(
        source="talent.id",
        read_only=True
    )

    class Meta:

        model = TalentScore

        fields = [
            "talent_id",
            "physical_score",
            "performance_score",
            "achievement_score",
            "experience_score",
            "verification_score",
            "overall_score",
        ]

        read_only_fields = fields
        
        
        
# =====================================================
# RECOMMENDATION HISTORY SERIALIZER
# =====================================================

class RecommendationHistorySerializer(serializers.ModelSerializer):

    talent_id = serializers.IntegerField(
        source="talent.id",
        read_only=True
    )

    talent_name = serializers.CharField(
        source="talent.user.get_full_name",
        read_only=True
    )

    opportunity_id = serializers.IntegerField(
        source="opportunity.id",
        read_only=True
    )

    opportunity_title = serializers.CharField(
        source="opportunity.title",
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

        model = RecommendationHistory

        fields = [
            "id",

            "talent_id",
            "talent_name",

            "opportunity_id",
            "opportunity_title",

            "organization_id",
            "organization_name",

            "score",
        ]

        read_only_fields = fields
        
        
# =====================================================
# TALENT PROFILE VIEW SERIALIZER
# =====================================================

class TalentProfileViewSerializer(serializers.ModelSerializer):

    talent_id = serializers.IntegerField(
        source="talent.id",
        read_only=True
    )

    talent_name = serializers.CharField(
        source="talent.user.get_full_name",
        read_only=True
    )

    viewer_id = serializers.IntegerField(
        source="viewer.id",
        read_only=True
    )

    viewer_username = serializers.CharField(
        source="viewer.username",
        read_only=True
    )

    class Meta:

        model = TalentProfileView

        fields = [
            "id",
            "talent_id",
            "talent_name",
            "viewer_id",
            "viewer_username",
            "created_at",
        ]

        read_only_fields = fields    
        
        
        

# =====================================================
# INVITATION SERIALIZER
# =====================================================

class InvitationSerializer(serializers.ModelSerializer):

    organization_id = serializers.IntegerField(
        source="organization.id",
        read_only=True
    )

    organization_name = serializers.CharField(
        source="organization.name",
        read_only=True
    )

    talent_id = serializers.IntegerField(
        source="talent.id",
        read_only=True
    )

    talent_name = serializers.CharField(
        source="talent.user.get_full_name",
        read_only=True
    )

    talent_username = serializers.CharField(
        source="talent.user.username",
        read_only=True
    )

    opportunity_id = serializers.IntegerField(
        source="opportunity.id",
        read_only=True
    )

    opportunity_title = serializers.CharField(
        source="opportunity.title",
        read_only=True
    )

    class Meta:

        model = Invitation

        fields = [
            "id",

            # Organization
            "organization_id",
            "organization_name",

            # Talent
            "talent_id",
            "talent_name",
            "talent_username",

            # Opportunity
            "opportunity_id",
            "opportunity_title",

            # Invitation
            "message",
            "status",

            # Metadata
            "created_at",
            "responded_at",
        ]

        read_only_fields = [
            "id",
            "organization_id",
            "organization_name",
            "talent_id",
            "talent_name",
            "talent_username",
            "opportunity_id",
            "opportunity_title",
            "status",
            "created_at",
            "responded_at",
        ]


# =====================================================
# INVITATION CREATE SERIALIZER
# =====================================================

class InvitationCreateSerializer(serializers.ModelSerializer):

    class Meta:

        model = Invitation

        fields = [
            "talent",
            "opportunity",
            "message",
        ] 
        
        
        
# =====================================================
# CONNECTION SERIALIZER
# =====================================================

class ConnectionSerializer(serializers.ModelSerializer):

    sender_id = serializers.IntegerField(
        source="sender.id",
        read_only=True
    )

    sender_username = serializers.CharField(
        source="sender.username",
        read_only=True
    )

    sender_name = serializers.CharField(
        source="sender.get_full_name",
        read_only=True
    )

    receiver_id = serializers.IntegerField(
        source="receiver.id",
        read_only=True
    )

    receiver_username = serializers.CharField(
        source="receiver.username",
        read_only=True
    )

    receiver_name = serializers.CharField(
        source="receiver.get_full_name",
        read_only=True
    )

    class Meta:

        model = Connection

        fields = [
            "id",

            "sender_id",
            "sender_username",
            "sender_name",

            "receiver_id",
            "receiver_username",
            "receiver_name",

            "status",

            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",

            "sender_id",
            "sender_username",
            "sender_name",

            "receiver_id",
            "receiver_username",
            "receiver_name",

            "status",

            "created_at",
            "updated_at",
        ]                                            
        
        
        
# =====================================================
# NOTIFICATION SERIALIZER
# =====================================================

class NotificationSerializer(serializers.ModelSerializer):

    sender_id = serializers.IntegerField(
        source="sender.id",
        read_only=True
    )

    sender_username = serializers.CharField(
        source="sender.username",
        read_only=True,
        allow_null=True
    )

    sender_name = serializers.CharField(
        source="sender.get_full_name",
        read_only=True,
        allow_null=True
    )

    notification_type_display = serializers.CharField(
        source="get_notification_type_display",
        read_only=True
    )

    post_id = serializers.IntegerField(
        source="post.id",
        read_only=True,
        allow_null=True
    )

    opportunity_id = serializers.IntegerField(
        source="opportunity.id",
        read_only=True,
        allow_null=True
    )

    conversation_id = serializers.IntegerField(
        source="conversation.id",
        read_only=True,
        allow_null=True
    )

    class Meta:

        model = Notification

        fields = [
            "id",

            # Notification
            "notification_type",
            "notification_type_display",
            "message",
            "is_read",

            # Sender
            "sender_id",
            "sender_username",
            "sender_name",

            # Related objects
            "post_id",
            "opportunity_id",
            "conversation_id",

            # Metadata
            "created_at",
        ]

        read_only_fields = [
            "id",
            "notification_type",
            "notification_type_display",
            "message",
            "sender_id",
            "sender_username",
            "sender_name",
            "post_id",
            "opportunity_id",
            "conversation_id",
            "created_at",
        ]        
        
        
        
# =====================================================
# SHORTLIST SERIALIZER
# =====================================================

class ShortlistSerializer(serializers.ModelSerializer):

    organization_id = serializers.IntegerField(
        source="organization.id",
        read_only=True
    )

    organization_name = serializers.CharField(
        source="organization.name",
        read_only=True
    )

    talent_id = serializers.IntegerField(
        source="talent.id",
        read_only=True
    )

    talent_name = serializers.CharField(
        source="talent.user.get_full_name",
        read_only=True
    )

    talent_username = serializers.CharField(
        source="talent.user.username",
        read_only=True
    )

    class Meta:

        model = Shortlist

        fields = [
            "id",

            # Organization
            "organization_id",
            "organization_name",

            # Talent
            "talent_id",
            "talent_name",
            "talent_username",

            # Shortlist
            "notes",
            "starred",

            # Metadata
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "organization_id",
            "organization_name",
            "talent_id",
            "talent_name",
            "talent_username",
            "created_at",
            "updated_at",
       
        ]  
        
        
        
        
# =====================================================
# RECRUITMENT STAGE SERIALIZER
# =====================================================

class RecruitmentStageSerializer(serializers.ModelSerializer):

    organization_id = serializers.IntegerField(
        source="organization.id",
        read_only=True
    )

    organization_name = serializers.CharField(
        source="organization.name",
        read_only=True
    )

    talent_id = serializers.IntegerField(
        source="talent.id",
        read_only=True
    )

    talent_name = serializers.CharField(
        source="talent.user.get_full_name",
        read_only=True
    )

    talent_username = serializers.CharField(
        source="talent.user.username",
        read_only=True
    )

    opportunity_id = serializers.IntegerField(
        source="opportunity.id",
        read_only=True
    )

    opportunity_title = serializers.CharField(
        source="opportunity.title",
        read_only=True
    )

    stage_display = serializers.CharField(
        source="get_stage_display",
        read_only=True
    )

    class Meta:

        model = RecruitmentStage

        fields = [
            "id",

            "organization_id",
            "organization_name",

            "talent_id",
            "talent_name",
            "talent_username",

            "opportunity_id",
            "opportunity_title",

            "stage",
            "stage_display",
            "notes",

            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "organization_id",
            "organization_name",
            "talent_id",
            "talent_name",
            "talent_username",
            "opportunity_id",
            "opportunity_title",
            "stage_display",
            "created_at",
            "updated_at",
        ]   
        
        
        
# =====================================================
# INVITATION SERIALIZER
# =====================================================

class InvitationSerializer(serializers.ModelSerializer):

    organization_id = serializers.IntegerField(
        source="organization.id",
        read_only=True
    )

    organization_name = serializers.CharField(
        source="organization.name",
        read_only=True
    )

    talent_id = serializers.IntegerField(
        source="talent.id",
        read_only=True
    )

    talent_name = serializers.CharField(
        source="talent.user.get_full_name",
        read_only=True
    )

    talent_username = serializers.CharField(
        source="talent.user.username",
        read_only=True
    )

    opportunity_id = serializers.IntegerField(
        source="opportunity.id",
        read_only=True
    )

    opportunity_title = serializers.CharField(
        source="opportunity.title",
        read_only=True
    )

    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True
    )

    class Meta:

        model = Invitation

        fields = [
            "id",

            # Organization
            "organization_id",
            "organization_name",

            # Talent
            "talent_id",
            "talent_name",
            "talent_username",

            # Opportunity
            "opportunity_id",
            "opportunity_title",

            # Invitation
            "message",
            "status",
            "status_display",

            # Metadata
            "created_at",
            "responded_at",
        ]

        read_only_fields = [
            "id",
            "organization_id",
            "organization_name",
            "talent_id",
            "talent_name",
            "talent_username",
            "opportunity_id",
            "opportunity_title",
            "status",
            "status_display",
            "created_at",
            "responded_at",
        ] 
        
        
# =====================================================
# CONNECTION SERIALIZER
# =====================================================

class ConnectionSerializer(serializers.ModelSerializer):

    sender_id = serializers.IntegerField(
        source="sender.id",
        read_only=True
    )

    sender_username = serializers.CharField(
        source="sender.username",
        read_only=True
    )

    sender_name = serializers.CharField(
        source="sender.get_full_name",
        read_only=True
    )

    receiver_id = serializers.IntegerField(
        source="receiver.id",
        read_only=True
    )

    receiver_username = serializers.CharField(
        source="receiver.username",
        read_only=True
    )

    receiver_name = serializers.CharField(
        source="receiver.get_full_name",
        read_only=True
    )

    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True
    )

    class Meta:

        model = Connection

        fields = [
            "id",

            "sender_id",
            "sender_username",
            "sender_name",

            "receiver_id",
            "receiver_username",
            "receiver_name",

            "status",
            "status_display",

            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",

            "sender_id",
            "sender_username",
            "sender_name",

            "receiver_id",
            "receiver_username",
            "receiver_name",

            "status",
            "status_display",

            "created_at",
            "updated_at",
        ]  
        
        
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

    follower_name = serializers.CharField(
        source="follower.get_full_name",
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

    following_name = serializers.CharField(
        source="following.get_full_name",
        read_only=True
    )

    class Meta:

        model = Follow

        fields = [
            "id",

            "follower_id",
            "follower_username",
            "follower_name",

            "following_id",
            "following_username",
            "following_name",

            "created_at",
        ]

        read_only_fields = [
            "id",
            "follower_id",
            "follower_username",
            "follower_name",
            "following_id",
            "following_username",
            "following_name",
            "created_at",
        ]                               
        
# =====================================================
# FOLLOW USER API
# =====================================================

class FollowUserAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        following_id = request.data.get(
            "following"
        )

        if not following_id:

            return Response(
                {
                    "detail": "Following user is required."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------
        # GET USER
        # ---------------------------------------------

        try:

            following = User.objects.get(
                id=following_id
            )

        except User.DoesNotExist:

            return Response(
                {
                    "detail": "User not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ---------------------------------------------
        # PREVENT SELF FOLLOW
        # ---------------------------------------------

        if following == request.user:

            return Response(
                {
                    "detail": "You cannot follow yourself."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------
        # CHECK EXISTING FOLLOW
        # ---------------------------------------------

        existing_follow = Follow.objects.filter(
            follower=request.user,
            following=following
        ).first()

        if existing_follow:

            return Response(
                {
                    "detail": "You are already following this user."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------
        # CREATE FOLLOW
        # ---------------------------------------------

        follow = Follow.objects.create(
            follower=request.user,
            following=following
        )

        # ---------------------------------------------
        # NOTIFICATION
        # ---------------------------------------------

        Notification.objects.create(
            user=following,
            sender=request.user,
            notification_type="FOLLOW",
            message=(
                f"{request.user.get_full_name() or request.user.username} "
                "started following you."
            )
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

        deleted, _ = Follow.objects.filter(
            follower=request.user,
            following_id=user_id
        ).delete()

        if deleted == 0:

            return Response(
                {
                    "detail": "You are not following this user."
                },
                status=status.HTTP_404_NOT_FOUND
            )

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
                "follower",
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
                "follower",
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
# ORGANIZATION FOLLOW SERIALIZER
# =====================================================

class OrganizationFollowSerializer(
    serializers.ModelSerializer
):

    user_id = serializers.IntegerField(
        source="user.id",
        read_only=True
    )

    username = serializers.CharField(
        source="user.username",
        read_only=True
    )

    user_name = serializers.CharField(
        source="user.get_full_name",
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
            "user_name",

            "organization_id",
            "organization_name",

            "created_at",
        ]

        read_only_fields = [
            "id",
            "user_id",
            "username",
            "user_name",
            "organization_id",
            "organization_name",
            "created_at",
        ]
        
        
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
        # CHECK EXISTING FOLLOW
        # ---------------------------------------------

        existing = OrganizationFollow.objects.filter(
            user=request.user,
            organization=organization
        ).first()

        if existing:

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
        # CREATE FOLLOW
        # ---------------------------------------------

        organization_follow = (
            OrganizationFollow.objects.create(
                user=request.user,
                organization=organization
            )
        )

        # ---------------------------------------------
        # NOTIFICATION
        # ---------------------------------------------

        if hasattr(organization, "user"):

            Notification.objects.create(
                user=organization.user,
                sender=request.user,
                notification_type="FOLLOW",
                message=(
                    f"{request.user.get_full_name() or request.user.username} "
                    "started following your organization."
                )
            )

        serializer = OrganizationFollowSerializer(
            organization_follow
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

        deleted, _ = (
            OrganizationFollow.objects.filter(
                user=request.user,
                organization_id=organization_id
            ).delete()
        )

        if deleted == 0:

            return Response(
                {
                    "detail": (
                        "You are not following "
                        "this organization."
                    )
                },
                status=status.HTTP_404_NOT_FOUND
            )

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
                "user",
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
# ROLE MODEL ASSIGNMENT SERIALIZER
# =====================================================

class RoleModelAssignmentSerializer(
    serializers.ModelSerializer
):

    talent_username = serializers.CharField(
        source="talent.user.username",
        read_only=True
    )

    assigned_by_username = serializers.CharField(
        source="assigned_by.username",
        read_only=True
    )

    reviewed_by_username = serializers.CharField(
        source="reviewed_by.username",
        read_only=True
    )

    class Meta:

        model = RoleModelAssignment

        fields = [
            "id",

            # Talent
            "talent",
            "talent_username",

            # Assignment
            "status",
            "assignment_type",
            "score",
            "category",
            "reason",
            "admin_notes",

            # Assignment users
            "assigned_by",
            "assigned_by_username",
            "reviewed_by",
            "reviewed_by_username",

            # Dates
            "assigned_at",
            "reviewed_at",
            "completed_at",
            "revoked_at",

            # Metadata
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "score",

            "assigned_by",
            "assigned_by_username",

            "reviewed_by",
            "reviewed_by_username",

            "assigned_at",
            "reviewed_at",
            "completed_at",
            "revoked_at",

            "created_at",
            "updated_at",
        ]  
        
        
class RoleModelRecommendationSerializer(serializers.Serializer):

    role_model_id = serializers.IntegerField()
    role_model_name = serializers.CharField()
    role_model_username = serializers.CharField()
    score = serializers.FloatField()
    reasons = serializers.ListField(
        child=serializers.CharField()
    )


class CourseRecommendationSerializer(serializers.Serializer):

    course_id = serializers.IntegerField()
    course_title = serializers.CharField()
    score = serializers.FloatField()
    reasons = serializers.ListField(
        child=serializers.CharField()
    )


class EventRecommendationSerializer(serializers.Serializer):

    event_id = serializers.IntegerField()
    event_title = serializers.CharField()
    score = serializers.FloatField()
    reasons = serializers.ListField(
        child=serializers.CharField()
    )                                                                          
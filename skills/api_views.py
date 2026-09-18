
from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from talents.models import TalentProfile

from .models import (
    SkillCategory,
    Skill,
)

from .serializers import (
    SkillCategorySerializer,
    SkillSerializer,
)


# ============================================================
# SKILL CATEGORIES
# ============================================================

class SkillCategoryListAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        categories = SkillCategory.objects.all().order_by(
            "name"
        )

        serializer = SkillCategorySerializer(
            categories,
            many=True
        )

        return Response(serializer.data)


# ============================================================
# SKILLS
# ============================================================

class SkillListAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        skills = Skill.objects.select_related(
            "category"
        ).order_by(
            "name"
        )

        serializer = SkillSerializer(
            skills,
            many=True
        )

        return Response(serializer.data)


# ============================================================
# SKILL DETAIL
# ============================================================

class SkillDetailAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, skill_id):

        skill = get_object_or_404(
            Skill.objects.select_related(
                "category"
            ),
            id=skill_id
        )

        serializer = SkillSerializer(
            skill
        )

        return Response(serializer.data)


# ============================================================
# MY SKILLS
# ============================================================

class MySkillsAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        if request.user.role != "ATHLETE":

            return Response(
                {
                    "detail": (
                        "Only talent accounts "
                        "have talent skills."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        talent = getattr(
            request.user,
            "talent_profile",
            None
        )

        if talent is None:

            return Response(
                {
                    "detail": "Talent profile not found."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        skills = talent.skills.select_related(
            "category"
        ).order_by(
            "name"
        )

        serializer = SkillSerializer(
            skills,
            many=True
        )

        return Response(serializer.data)


# ============================================================
# TALENT SKILLS
# ============================================================

class TalentSkillsAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, talent_id):

        talent = get_object_or_404(
            TalentProfile,
            id=talent_id
        )

        skills = talent.skills.select_related(
            "category"
        ).order_by(
            "name"
        )

        serializer = SkillSerializer(
            skills,
            many=True
        )

        return Response(serializer.data)


# ============================================================
# ADD SKILL
# ============================================================

class AddSkillAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, skill_id):

        if request.user.role != "ATHLETE":

            return Response(
                {
                    "detail": (
                        "Only talent accounts "
                        "can add skills."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        talent = getattr(
            request.user,
            "talent_profile",
            None
        )

        if talent is None:

            return Response(
                {
                    "detail": "Talent profile not found."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        skill = get_object_or_404(
            Skill,
            id=skill_id
        )

        if talent.skills.filter(
            id=skill.id
        ).exists():

            return Response(
                {
                    "detail": "Skill already added."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        talent.skills.add(skill)

        return Response(
            SkillSerializer(skill).data,
            status=status.HTTP_201_CREATED
        )


# ============================================================
# REMOVE SKILL
# ============================================================

class RemoveSkillAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def delete(self, request, skill_id):

        if request.user.role != "ATHLETE":

            return Response(
                {
                    "detail": (
                        "Only talent accounts "
                        "can remove skills."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        talent = getattr(
            request.user,
            "talent_profile",
            None
        )

        if talent is None:

            return Response(
                {
                    "detail": "Talent profile not found."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        skill = get_object_or_404(
            Skill,
            id=skill_id
        )

        if not talent.skills.filter(
            id=skill.id
        ).exists():

            return Response(
                {
                    "detail": "Skill is not in your profile."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        talent.skills.remove(skill)

        return Response(
            {
                "detail": "Skill removed successfully."
            },
            status=status.HTTP_204_NO_CONTENT
        )


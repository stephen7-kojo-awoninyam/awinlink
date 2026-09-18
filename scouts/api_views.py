from django.shortcuts import get_object_or_404

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    ScoutProfile,
    ScoutTalentView,
    ScoutTalentFollow,
    ScoutTalentBookmark,
)

from .serializers import (
    ScoutProfileSerializer,
    ScoutTalentViewSerializer,
    ScoutTalentFollowSerializer,
    ScoutTalentBookmarkSerializer,
)

from talents.models import TalentProfile


# ============================================================
# MY SCOUT PROFILE
# ============================================================

class MyScoutProfileAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        if request.user.role != "SCOUT":

            return Response(
                {
                    "detail": "Only scout accounts can access this."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        profile = get_object_or_404(
            ScoutProfile,
            user=request.user
        )

        serializer = ScoutProfileSerializer(profile)

        return Response(serializer.data)


# ============================================================
# UPDATE MY SCOUT PROFILE
# ============================================================

class MyScoutProfileUpdateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def patch(self, request):

        if request.user.role != "SCOUT":

            return Response(
                {
                    "detail": "Only scout accounts can update a scout profile."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        profile = get_object_or_404(
            ScoutProfile,
            user=request.user
        )

        serializer = ScoutProfileSerializer(
            profile,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():

            serializer.save()

            return Response(serializer.data)

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


# ============================================================
# SCOUT TALENT DIRECTORY
# ============================================================

class ScoutTalentListAPIView(generics.ListAPIView):

    permission_classes = [IsAuthenticated]

    serializer_class = ScoutTalentViewSerializer

    def get_queryset(self):

        if self.request.user.role != "SCOUT":

            return ScoutTalentView.objects.none()

        scout = getattr(
            self.request.user,
            "scout_profile",
            None
        )

        if scout is None:

            return ScoutTalentView.objects.none()

        return ScoutTalentView.objects.filter(
            scout=scout
        ).select_related(
            "talent",
            "talent__user"
        )


# ============================================================
# VIEW TALENT
# ============================================================

class ScoutViewTalentAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, talent_id):

        if request.user.role != "SCOUT":

            return Response(
                {
                    "detail": "Only scout accounts can view talents."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        scout = get_object_or_404(
            ScoutProfile,
            user=request.user
        )

        talent = get_object_or_404(
            TalentProfile,
            id=talent_id
        )

        talent_view = ScoutTalentView.objects.create(
            scout=scout,
            talent=talent
        )

        return Response(
            ScoutTalentViewSerializer(
                talent_view
            ).data,
            status=status.HTTP_201_CREATED
        )


# ============================================================
# MY TALENT VIEWS
# ============================================================

class MyScoutTalentViewsAPIView(generics.ListAPIView):

    permission_classes = [IsAuthenticated]

    serializer_class = ScoutTalentViewSerializer

    def get_queryset(self):

        if self.request.user.role != "SCOUT":

            return ScoutTalentView.objects.none()

        scout = getattr(
            self.request.user,
            "scout_profile",
            None
        )

        if scout is None:

            return ScoutTalentView.objects.none()

        return ScoutTalentView.objects.filter(
            scout=scout
        ).select_related(
            "talent",
            "talent__user"
        )


# ============================================================
# FOLLOW TALENT
# ============================================================

class ScoutFollowTalentAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, talent_id):

        if request.user.role != "SCOUT":

            return Response(
                {
                    "detail": "Only scout accounts can follow talents."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        scout = get_object_or_404(
            ScoutProfile,
            user=request.user
        )

        talent = get_object_or_404(
            TalentProfile,
            id=talent_id
        )

        follow, created = ScoutTalentFollow.objects.get_or_create(
            scout=scout,
            talent=talent
        )

        if not created:

            return Response(
                {
                    "detail": "You already follow this talent."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            ScoutTalentFollowSerializer(
                follow
            ).data,
            status=status.HTTP_201_CREATED
        )


# ============================================================
# UNFOLLOW TALENT
# ============================================================

class ScoutUnfollowTalentAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def delete(self, request, talent_id):

        if request.user.role != "SCOUT":

            return Response(
                {
                    "detail": "Only scout accounts can unfollow talents."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        scout = get_object_or_404(
            ScoutProfile,
            user=request.user
        )

        follow = get_object_or_404(
            ScoutTalentFollow,
            scout=scout,
            talent_id=talent_id
        )

        follow.delete()

        return Response(
            {
                "detail": "Talent unfollowed successfully."
            },
            status=status.HTTP_200_OK
        )


# ============================================================
# MY FOLLOWED TALENTS
# ============================================================

class MyFollowedTalentsAPIView(generics.ListAPIView):

    permission_classes = [IsAuthenticated]

    serializer_class = ScoutTalentFollowSerializer

    def get_queryset(self):

        if self.request.user.role != "SCOUT":

            return ScoutTalentFollow.objects.none()

        scout = getattr(
            self.request.user,
            "scout_profile",
            None
        )

        if scout is None:

            return ScoutTalentFollow.objects.none()

        return ScoutTalentFollow.objects.filter(
            scout=scout
        ).select_related(
            "talent",
            "talent__user"
        )


# ============================================================
# BOOKMARK TALENT
# ============================================================

class ScoutBookmarkTalentAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, talent_id):

        if request.user.role != "SCOUT":

            return Response(
                {
                    "detail": "Only scout accounts can bookmark talents."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        scout = get_object_or_404(
            ScoutProfile,
            user=request.user
        )

        talent = get_object_or_404(
            TalentProfile,
            id=talent_id
        )

        bookmark, created = ScoutTalentBookmark.objects.get_or_create(
            scout=scout,
            talent=talent,
            defaults={
                "notes": request.data.get(
                    "notes",
                    ""
                )
            }
        )

        if not created:

            return Response(
                {
                    "detail": "Talent is already bookmarked."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            ScoutTalentBookmarkSerializer(
                bookmark
            ).data,
            status=status.HTTP_201_CREATED
        )


# ============================================================
# UPDATE BOOKMARK
# ============================================================

class ScoutBookmarkUpdateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def patch(self, request, bookmark_id):

        if request.user.role != "SCOUT":

            return Response(
                {
                    "detail": "Only scout accounts can update bookmarks."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        scout = get_object_or_404(
            ScoutProfile,
            user=request.user
        )

        bookmark = get_object_or_404(
            ScoutTalentBookmark,
            id=bookmark_id,
            scout=scout
        )

        serializer = ScoutTalentBookmarkSerializer(
            bookmark,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():

            serializer.save()

            return Response(serializer.data)

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


# ============================================================
# REMOVE BOOKMARK
# ============================================================

class ScoutBookmarkDeleteAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def delete(self, request, bookmark_id):

        if request.user.role != "SCOUT":

            return Response(
                {
                    "detail": "Only scout accounts can delete bookmarks."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        scout = get_object_or_404(
            ScoutProfile,
            user=request.user
        )

        bookmark = get_object_or_404(
            ScoutTalentBookmark,
            id=bookmark_id,
            scout=scout
        )

        bookmark.delete()

        return Response(
            {
                "detail": "Bookmark removed successfully."
            },
            status=status.HTTP_200_OK
        )


# ============================================================
# MY BOOKMARKS
# ============================================================

class MyScoutBookmarksAPIView(generics.ListAPIView):

    permission_classes = [IsAuthenticated]

    serializer_class = ScoutTalentBookmarkSerializer

    def get_queryset(self):

        if self.request.user.role != "SCOUT":

            return ScoutTalentBookmark.objects.none()

        scout = getattr(
            self.request.user,
            "scout_profile",
            None
        )

        if scout is None:

            return ScoutTalentBookmark.objects.none()

        return ScoutTalentBookmark.objects.filter(
            scout=scout
        ).select_related(
            "talent",
            "talent__user"
        )
from django.shortcuts import get_object_or_404

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from talents.models import TalentProfile
from api.serializers import TalentProfileSerializer

from .models import (
    CoachProfile,
    CoachTalentView,
    CoachTalentFollow,
    CoachTalentBookmark,
)

from .serializers import (
    CoachProfileSerializer,
    CoachTalentViewSerializer,
    CoachTalentFollowSerializer,
    CoachTalentBookmarkSerializer,
)


# ============================================================
# MY COACH PROFILE
# ============================================================

class MyCoachProfileAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        if request.user.role != "COACH":

            return Response(
                {
                    "detail": "Only coach accounts can access this."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        profile = get_object_or_404(
            CoachProfile,
            user=request.user
        )

        serializer = CoachProfileSerializer(profile)

        return Response(serializer.data)


# ============================================================
# UPDATE MY COACH PROFILE
# ============================================================

class MyCoachProfileUpdateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def patch(self, request):

        if request.user.role != "COACH":

            return Response(
                {
                    "detail": (
                        "Only coach accounts can "
                        "update a coach profile."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        profile = get_object_or_404(
            CoachProfile,
            user=request.user
        )

        serializer = CoachProfileSerializer(
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
# TALENT DISCOVERY
# ============================================================

class CoachTalentListAPIView(generics.ListAPIView):

    permission_classes = [IsAuthenticated]

    serializer_class = TalentProfileSerializer

    def get_queryset(self):

        if self.request.user.role != "COACH":

            return TalentProfile.objects.none()

        return TalentProfile.objects.select_related(
            "user"
        ).prefetch_related(
            "skills",
            "domains",
        ).order_by(
            "-created_at"
        )


# ============================================================
# VIEW TALENT
# ============================================================

class CoachViewTalentAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, talent_id):

        if request.user.role != "COACH":

            return Response(
                {
                    "detail": (
                        "Only coach accounts can "
                        "view talents."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        coach = get_object_or_404(
            CoachProfile,
            user=request.user
        )

        talent = get_object_or_404(
            TalentProfile,
            id=talent_id
        )

        talent_view = CoachTalentView.objects.create(
            coach=coach,
            talent=talent
        )

        return Response(
            CoachTalentViewSerializer(
                talent_view
            ).data,
            status=status.HTTP_201_CREATED
        )


# ============================================================
# MY TALENT VIEWS
# ============================================================

class MyCoachTalentViewsAPIView(generics.ListAPIView):

    permission_classes = [IsAuthenticated]

    serializer_class = CoachTalentViewSerializer

    def get_queryset(self):

        if self.request.user.role != "COACH":

            return CoachTalentView.objects.none()

        coach = getattr(
            self.request.user,
            "coach_profile",
            None
        )

        if coach is None:

            return CoachTalentView.objects.none()

        return CoachTalentView.objects.filter(
            coach=coach
        ).select_related(
            "talent",
            "talent__user"
        )


# ============================================================
# FOLLOW TALENT
# ============================================================

class CoachFollowTalentAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, talent_id):

        if request.user.role != "COACH":

            return Response(
                {
                    "detail": (
                        "Only coach accounts can "
                        "follow talents."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        coach = get_object_or_404(
            CoachProfile,
            user=request.user
        )

        talent = get_object_or_404(
            TalentProfile,
            id=talent_id
        )

        follow, created = CoachTalentFollow.objects.get_or_create(
            coach=coach,
            talent=talent
        )

        if not created:

            return Response(
                {
                    "detail": (
                        "You already follow "
                        "this talent."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            CoachTalentFollowSerializer(
                follow
            ).data,
            status=status.HTTP_201_CREATED
        )


# ============================================================
# UNFOLLOW TALENT
# ============================================================

class CoachUnfollowTalentAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def delete(self, request, talent_id):

        if request.user.role != "COACH":

            return Response(
                {
                    "detail": (
                        "Only coach accounts can "
                        "unfollow talents."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        coach = get_object_or_404(
            CoachProfile,
            user=request.user
        )

        follow = get_object_or_404(
            CoachTalentFollow,
            coach=coach,
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

    serializer_class = CoachTalentFollowSerializer

    def get_queryset(self):

        if self.request.user.role != "COACH":

            return CoachTalentFollow.objects.none()

        coach = getattr(
            self.request.user,
            "coach_profile",
            None
        )

        if coach is None:

            return CoachTalentFollow.objects.none()

        return CoachTalentFollow.objects.filter(
            coach=coach
        ).select_related(
            "talent",
            "talent__user"
        )


# ============================================================
# BOOKMARK TALENT
# ============================================================

class CoachBookmarkTalentAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, talent_id):

        if request.user.role != "COACH":

            return Response(
                {
                    "detail": (
                        "Only coach accounts can "
                        "bookmark talents."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        coach = get_object_or_404(
            CoachProfile,
            user=request.user
        )

        talent = get_object_or_404(
            TalentProfile,
            id=talent_id
        )

        bookmark, created = CoachTalentBookmark.objects.get_or_create(
            coach=coach,
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
                    "detail": (
                        "Talent is already "
                        "bookmarked."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            CoachTalentBookmarkSerializer(
                bookmark
            ).data,
            status=status.HTTP_201_CREATED
        )


# ============================================================
# UPDATE BOOKMARK
# ============================================================

class CoachBookmarkUpdateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def patch(self, request, bookmark_id):

        if request.user.role != "COACH":

            return Response(
                {
                    "detail": (
                        "Only coach accounts can "
                        "update bookmarks."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        coach = get_object_or_404(
            CoachProfile,
            user=request.user
        )

        bookmark = get_object_or_404(
            CoachTalentBookmark,
            id=bookmark_id,
            coach=coach
        )

        serializer = CoachTalentBookmarkSerializer(
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
# DELETE BOOKMARK
# ============================================================

class CoachBookmarkDeleteAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def delete(self, request, bookmark_id):

        if request.user.role != "COACH":

            return Response(
                {
                    "detail": (
                        "Only coach accounts can "
                        "delete bookmarks."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        coach = get_object_or_404(
            CoachProfile,
            user=request.user
        )

        bookmark = get_object_or_404(
            CoachTalentBookmark,
            id=bookmark_id,
            coach=coach
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

class MyCoachBookmarksAPIView(generics.ListAPIView):

    permission_classes = [IsAuthenticated]

    serializer_class = CoachTalentBookmarkSerializer

    def get_queryset(self):

        if self.request.user.role != "COACH":

            return CoachTalentBookmark.objects.none()

        coach = getattr(
            self.request.user,
            "coach_profile",
            None
        )

        if coach is None:

            return CoachTalentBookmark.objects.none()

        return CoachTalentBookmark.objects.filter(
            coach=coach
        ).select_related(
            "talent",
            "talent__user"
        )
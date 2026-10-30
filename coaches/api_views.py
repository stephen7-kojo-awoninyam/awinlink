from accounts.roles import active_user_has_role
from api.search import BoundedSearchFilter, TALENT_SEARCH_FIELDS
from django.utils.decorators import method_decorator
from talents.visibility import public_talent_profiles_for
from django.views.decorators.cache import never_cache
from django.shortcuts import get_object_or_404

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from talents.models import TalentProfile
from api.serializers import TalentProfileSerializer, SpecialistTalentProfileSerializer
from django.db.models import OuterRef, Subquery

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

@method_decorator(never_cache, name='dispatch')
class MyCoachProfileAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        if not active_user_has_role(request.user, "COACH"):

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

@method_decorator(never_cache, name='dispatch')
class MyCoachProfileUpdateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def patch(self, request):

        if not active_user_has_role(request.user, "COACH"):

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

@method_decorator(never_cache, name='dispatch')
class CoachTalentListAPIView(generics.ListAPIView):
    filter_backends = [BoundedSearchFilter]
    search_fields = TALENT_SEARCH_FIELDS

    permission_classes = [IsAuthenticated]

    serializer_class = SpecialistTalentProfileSerializer

    def get_queryset(self):

        if not active_user_has_role(self.request.user, "COACH"):

            return public_talent_profiles_for(self.request.user).none()

        return public_talent_profiles_for(self.request.user).select_related(
            "user", "other_profile"
        ).prefetch_related(
            "skills",
            "domains",
            "achievements", "certifications", "experiences",
        ).filter(
            profile_visibility="PUBLIC"
        ).order_by(
            "-created_at"
        ).annotate(
            _viewer_bookmark_id=Subquery(CoachTalentBookmark.objects.filter(coach__user=self.request.user, talent_id=OuterRef('pk')).values('pk')[:1]),
            _viewer_follow_id=Subquery(CoachTalentFollow.objects.filter(coach__user=self.request.user, talent_id=OuterRef('pk')).values('pk')[:1]),
        )


# ============================================================
# VIEW TALENT
# ============================================================

@method_decorator(never_cache, name='dispatch')
class CoachViewTalentAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, talent_id):

        if not active_user_has_role(request.user, "COACH"):

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
            public_talent_profiles_for(self.request.user),
            id=talent_id,
            profile_visibility="PUBLIC",
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

@method_decorator(never_cache, name='dispatch')
class MyCoachTalentViewsAPIView(generics.ListAPIView):

    permission_classes = [IsAuthenticated]

    serializer_class = CoachTalentViewSerializer

    def get_queryset(self):

        if not active_user_has_role(self.request.user, "COACH"):

            return CoachTalentView.objects.none()

        coach = getattr(
            self.request.user,
            "coach_profile",
            None
        )

        if coach is None:

            return CoachTalentView.objects.none()

        return CoachTalentView.objects.filter(
            coach=coach,
            talent__in=public_talent_profiles_for(self.request.user),
        ).select_related(
            "talent",
            "talent__user"
        )


# ============================================================
# FOLLOW TALENT
# ============================================================

@method_decorator(never_cache, name='dispatch')
class CoachFollowTalentAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, talent_id):

        if not active_user_has_role(request.user, "COACH"):

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
            public_talent_profiles_for(self.request.user),
            id=talent_id,
            profile_visibility="PUBLIC",
        )

        follow, created = CoachTalentFollow.objects.get_or_create(
            coach=coach,
            talent=talent
        )

        return Response(
            CoachTalentFollowSerializer(
                follow
            ).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


# ============================================================
# UNFOLLOW TALENT
# ============================================================

@method_decorator(never_cache, name='dispatch')
class CoachUnfollowTalentAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def delete(self, request, talent_id):

        if not active_user_has_role(request.user, "COACH"):

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

        CoachTalentFollow.objects.filter(
            coach=coach,
            talent_id=talent_id,
        ).delete()

        return Response(
            {
                "detail": "Talent unfollowed successfully."
            },
            status=status.HTTP_200_OK
        )


# ============================================================
# MY FOLLOWED TALENTS
# ============================================================

@method_decorator(never_cache, name='dispatch')
class MyFollowedTalentsAPIView(generics.ListAPIView):

    permission_classes = [IsAuthenticated]

    serializer_class = CoachTalentFollowSerializer

    def get_queryset(self):

        if not active_user_has_role(self.request.user, "COACH"):

            return CoachTalentFollow.objects.none()

        coach = getattr(
            self.request.user,
            "coach_profile",
            None
        )

        if coach is None:

            return CoachTalentFollow.objects.none()

        return CoachTalentFollow.objects.filter(
            coach=coach,
            talent__in=public_talent_profiles_for(self.request.user),
        ).select_related(
            "talent",
            "talent__user"
        )


# ============================================================
# BOOKMARK TALENT
# ============================================================

@method_decorator(never_cache, name='dispatch')
class CoachBookmarkTalentAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, talent_id):

        if not active_user_has_role(request.user, "COACH"):

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
            public_talent_profiles_for(self.request.user),
            id=talent_id,
            profile_visibility="PUBLIC",
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

@method_decorator(never_cache, name='dispatch')
class CoachBookmarkUpdateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def patch(self, request, bookmark_id):

        if not active_user_has_role(request.user, "COACH"):

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
            coach=coach,
            talent__in=public_talent_profiles_for(self.request.user),
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

@method_decorator(never_cache, name='dispatch')
class CoachBookmarkDeleteAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def delete(self, request, bookmark_id):

        if not active_user_has_role(request.user, "COACH"):

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

@method_decorator(never_cache, name='dispatch')
class MyCoachBookmarksAPIView(generics.ListAPIView):

    permission_classes = [IsAuthenticated]

    serializer_class = CoachTalentBookmarkSerializer

    def get_queryset(self):

        if not active_user_has_role(self.request.user, "COACH"):

            return CoachTalentBookmark.objects.none()

        coach = getattr(
            self.request.user,
            "coach_profile",
            None
        )

        if coach is None:

            return CoachTalentBookmark.objects.none()

        return CoachTalentBookmark.objects.filter(
            coach=coach,
            talent__in=public_talent_profiles_for(self.request.user),
        ).select_related(
            "talent",
            "talent__user"
        )

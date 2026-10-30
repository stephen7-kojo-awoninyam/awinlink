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
from api.serializers import TalentProfileSerializer, SpecialistTalentProfileSerializer
from api.pagination import OrderedCursorPagination
from django.db.models import OuterRef, Subquery


# ============================================================
# MY SCOUT PROFILE
# ============================================================

@method_decorator(never_cache, name='dispatch')
class MyScoutProfileAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        if not active_user_has_role(request.user, "SCOUT"):

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

@method_decorator(never_cache, name='dispatch')
class MyScoutProfileUpdateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def patch(self, request):

        if not active_user_has_role(request.user, "SCOUT"):

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

class ScoutDirectoryPagination(OrderedCursorPagination):
    ordering = ('-verified', 'user__username', 'pk')


@method_decorator(never_cache, name='dispatch')
class ScoutTalentListAPIView(generics.ListAPIView):
    pagination_class = ScoutDirectoryPagination
    filter_backends = [BoundedSearchFilter]
    search_fields = TALENT_SEARCH_FIELDS

    permission_classes = [IsAuthenticated]

    serializer_class = SpecialistTalentProfileSerializer

    def get_queryset(self):

        if not active_user_has_role(self.request.user, "SCOUT"):

            return public_talent_profiles_for(self.request.user).none()

        return public_talent_profiles_for(self.request.user).filter(
            profile_visibility="PUBLIC",
        ).select_related(
            "user", "other_profile",
        ).prefetch_related(
            "skills",
            "domains",
            "achievements", "certifications", "experiences",
        ).order_by(
            "-verified",
            "user__username",
        ).annotate(
            _viewer_bookmark_id=Subquery(ScoutTalentBookmark.objects.filter(scout__user=self.request.user, talent_id=OuterRef('pk')).values('pk')[:1]),
            _viewer_follow_id=Subquery(ScoutTalentFollow.objects.filter(scout__user=self.request.user, talent_id=OuterRef('pk')).values('pk')[:1]),
        )


# ============================================================
# VIEW TALENT
# ============================================================

@method_decorator(never_cache, name='dispatch')
class ScoutViewTalentAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, talent_id):

        if not active_user_has_role(request.user, "SCOUT"):

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
            public_talent_profiles_for(self.request.user),
            id=talent_id,
            profile_visibility="PUBLIC",
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

@method_decorator(never_cache, name='dispatch')
class MyScoutTalentViewsAPIView(generics.ListAPIView):

    permission_classes = [IsAuthenticated]

    serializer_class = ScoutTalentViewSerializer

    def get_queryset(self):

        if not active_user_has_role(self.request.user, "SCOUT"):

            return ScoutTalentView.objects.none()

        scout = getattr(
            self.request.user,
            "scout_profile",
            None
        )

        if scout is None:

            return ScoutTalentView.objects.none()

        return ScoutTalentView.objects.filter(
            scout=scout,
            talent__in=public_talent_profiles_for(self.request.user),
        ).select_related(
            "talent",
            "talent__user"
        )


# ============================================================
# FOLLOW TALENT
# ============================================================

@method_decorator(never_cache, name='dispatch')
class ScoutFollowTalentAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, talent_id):

        if not active_user_has_role(request.user, "SCOUT"):

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
            public_talent_profiles_for(self.request.user),
            id=talent_id,
            profile_visibility="PUBLIC",
        )

        follow, created = ScoutTalentFollow.objects.get_or_create(
            scout=scout,
            talent=talent
        )

        return Response(
            ScoutTalentFollowSerializer(
                follow
            ).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


# ============================================================
# UNFOLLOW TALENT
# ============================================================

@method_decorator(never_cache, name='dispatch')
class ScoutUnfollowTalentAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def delete(self, request, talent_id):

        if not active_user_has_role(request.user, "SCOUT"):

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

        ScoutTalentFollow.objects.filter(
            scout=scout,
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

    serializer_class = ScoutTalentFollowSerializer

    def get_queryset(self):

        if not active_user_has_role(self.request.user, "SCOUT"):

            return ScoutTalentFollow.objects.none()

        scout = getattr(
            self.request.user,
            "scout_profile",
            None
        )

        if scout is None:

            return ScoutTalentFollow.objects.none()

        return ScoutTalentFollow.objects.filter(
            scout=scout,
            talent__in=public_talent_profiles_for(self.request.user),
        ).select_related(
            "talent",
            "talent__user"
        )


# ============================================================
# BOOKMARK TALENT
# ============================================================

@method_decorator(never_cache, name='dispatch')
class ScoutBookmarkTalentAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, talent_id):

        if not active_user_has_role(request.user, "SCOUT"):

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
            public_talent_profiles_for(self.request.user),
            id=talent_id,
            profile_visibility="PUBLIC",
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

@method_decorator(never_cache, name='dispatch')
class ScoutBookmarkUpdateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def patch(self, request, bookmark_id):

        if not active_user_has_role(request.user, "SCOUT"):

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
            scout=scout,
            talent__in=public_talent_profiles_for(self.request.user),
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

@method_decorator(never_cache, name='dispatch')
class ScoutBookmarkDeleteAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def delete(self, request, bookmark_id):

        if not active_user_has_role(request.user, "SCOUT"):

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

@method_decorator(never_cache, name='dispatch')
class MyScoutBookmarksAPIView(generics.ListAPIView):

    permission_classes = [IsAuthenticated]

    serializer_class = ScoutTalentBookmarkSerializer

    def get_queryset(self):

        if not active_user_has_role(self.request.user, "SCOUT"):

            return ScoutTalentBookmark.objects.none()

        scout = getattr(
            self.request.user,
            "scout_profile",
            None
        )

        if scout is None:

            return ScoutTalentBookmark.objects.none()

        return ScoutTalentBookmark.objects.filter(
            scout=scout,
            talent__in=public_talent_profiles_for(self.request.user),
        ).select_related(
            "talent",
            "talent__user"
        )

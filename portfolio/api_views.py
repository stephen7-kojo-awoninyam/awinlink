
from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from talents.models import TalentProfile

from .models import PortfolioItem
from .serializers import PortfolioItemSerializer


# ============================================================
# MY PORTFOLIO
# ============================================================

class MyPortfolioListAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        if request.user.role != "ATHLETE":

            return Response(
                {
                    "detail": (
                        "Only talent accounts "
                        "have a personal portfolio."
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

        portfolio_items = PortfolioItem.objects.filter(
            talent=talent
        ).order_by(
            "-created_at"
        )

        serializer = PortfolioItemSerializer(
            portfolio_items,
            many=True
        )

        return Response(serializer.data)


# ============================================================
# CREATE PORTFOLIO ITEM
# ============================================================

class PortfolioItemCreateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        if request.user.role != "ATHLETE":

            return Response(
                {
                    "detail": (
                        "Only talent accounts "
                        "can create portfolio items."
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

        serializer = PortfolioItemSerializer(
            data=request.data
        )

        if serializer.is_valid():

            portfolio_item = serializer.save(
                talent=talent
            )

            return Response(
                PortfolioItemSerializer(
                    portfolio_item
                ).data,
                status=status.HTTP_201_CREATED
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


# ============================================================
# PORTFOLIO ITEM DETAIL
# ============================================================

class PortfolioItemDetailAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, item_id):

        item = get_object_or_404(
            PortfolioItem,
            id=item_id
        )

        serializer = PortfolioItemSerializer(
            item
        )

        return Response(serializer.data)


# ============================================================
# UPDATE PORTFOLIO ITEM
# ============================================================

class PortfolioItemUpdateAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def patch(self, request, item_id):

        item = get_object_or_404(
            PortfolioItem,
            id=item_id
        )

        if request.user.role != "ATHLETE":

            return Response(
                {
                    "detail": (
                        "Only talent accounts "
                        "can update portfolio items."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        if item.talent.user != request.user:

            return Response(
                {
                    "detail": (
                        "You do not have permission "
                        "to update this portfolio item."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = PortfolioItemSerializer(
            item,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():

            serializer.save()

            return Response(
                serializer.data
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


# ============================================================
# DELETE PORTFOLIO ITEM
# ============================================================

class PortfolioItemDeleteAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def delete(self, request, item_id):

        item = get_object_or_404(
            PortfolioItem,
            id=item_id
        )

        if request.user.role != "ATHLETE":

            return Response(
                {
                    "detail": (
                        "Only talent accounts "
                        "can delete portfolio items."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        if item.talent.user != request.user:

            return Response(
                {
                    "detail": (
                        "You do not have permission "
                        "to delete this portfolio item."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        item.delete()

        return Response(
            {
                "detail": (
                    "Portfolio item deleted successfully."
                )
            },
            status=status.HTTP_204_NO_CONTENT
        )


# ============================================================
# TALENT PORTFOLIO
# ============================================================

class TalentPortfolioAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, talent_id):

        talent = get_object_or_404(
            TalentProfile,
            id=talent_id
        )

        portfolio_items = PortfolioItem.objects.filter(
            talent=talent
        ).order_by(
            "-created_at"
        )

        serializer = PortfolioItemSerializer(
            portfolio_items,
            many=True
        )

        return Response(serializer.data)


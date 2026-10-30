from api.pagination import PagedAPIView
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PortfolioItem
from .permissions import (owned_portfolio_item_for, owned_portfolio_talent_for,
    visible_portfolio_items_for, visible_portfolio_talent_for)
from .serializers import PortfolioItemSerializer


class PortfolioAPI(PagedAPIView):
    permission_classes = [IsAuthenticated]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        return response


class MyPortfolioListAPIView(PortfolioAPI):
    def get(self, request):
        talent = owned_portfolio_talent_for(request.user)
        items = PortfolioItem.objects.filter(talent=talent).select_related('talent__user').order_by('-created_at')
        return Response(PortfolioItemSerializer(self.page(request, items), many=True).data)


class PortfolioItemCreateAPIView(PortfolioAPI):
    def post(self, request):
        talent = owned_portfolio_talent_for(request.user)
        serializer = PortfolioItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(talent=talent)
        return Response(serializer.data, status=201)


class PortfolioItemDetailAPIView(PortfolioAPI):
    def get(self, request, item_id):
        item = get_object_or_404(visible_portfolio_items_for(request.user), pk=item_id)
        return Response(PortfolioItemSerializer(item).data)


class PortfolioItemUpdateAPIView(PortfolioAPI):
    def patch(self, request, item_id):
        item = owned_portfolio_item_for(request.user, item_id)
        serializer = PortfolioItemSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        from media_erasure.services import save_instance_with_media_retention
        save_instance_with_media_retention(item, serializer.save, requested_by_id=request.user.pk)
        return Response(serializer.data)


class PortfolioItemDeleteAPIView(PortfolioAPI):
    def delete(self, request, item_id):
        item = owned_portfolio_item_for(request.user, item_id)
        from media_erasure.services import delete_instance_with_retention
        delete_instance_with_retention(item, requested_by_id=request.user.pk)
        return Response(status=204)


class TalentPortfolioAPIView(PortfolioAPI):
    def get(self, request, talent_id):
        # Check the parent even when a portfolio is empty.
        talent = visible_portfolio_talent_for(request.user, talent_id)
        items = visible_portfolio_items_for(request.user).filter(talent=talent).order_by('-created_at')
        return Response(PortfolioItemSerializer(self.page(request, items), many=True).data)


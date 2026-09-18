
from django.urls import path

from .api_views import (
    MyPortfolioListAPIView,
    PortfolioItemCreateAPIView,
    PortfolioItemDetailAPIView,
    PortfolioItemUpdateAPIView,
    PortfolioItemDeleteAPIView,
    TalentPortfolioAPIView,
)


app_name = "portfolio_api"


urlpatterns = [

    # =====================================================
    # MY PORTFOLIO
    # =====================================================

    path(
        "my/",
        MyPortfolioListAPIView.as_view(),
        name="my_portfolio"
    ),

    # =====================================================
    # CREATE
    # =====================================================

    path(
        "create/",
        PortfolioItemCreateAPIView.as_view(),
        name="portfolio_create"
    ),

    # =====================================================
    # TALENT PORTFOLIO
    # =====================================================

    path(
        "talent/<int:talent_id>/",
        TalentPortfolioAPIView.as_view(),
        name="talent_portfolio"
    ),

    # =====================================================
    # DETAIL
    # =====================================================

    path(
        "<int:item_id>/",
        PortfolioItemDetailAPIView.as_view(),
        name="portfolio_detail"
    ),

    # =====================================================
    # UPDATE
    # =====================================================

    path(
        "<int:item_id>/update/",
        PortfolioItemUpdateAPIView.as_view(),
        name="portfolio_update"
    ),

    # =====================================================
    # DELETE
    # =====================================================

    path(
        "<int:item_id>/delete/",
        PortfolioItemDeleteAPIView.as_view(),
        name="portfolio_delete"
    ),

]


from django.urls import path

from .api_views import (
    TalentDomainListAPIView,
    TalentDomainDetailAPIView,
)


app_name = "domains_api"


urlpatterns = [

    # =====================================================
    # TALENT DOMAINS
    # =====================================================

    path(
        "",
        TalentDomainListAPIView.as_view(),
        name="domain_list"
    ),

    path(
        "<int:domain_id>/",
        TalentDomainDetailAPIView.as_view(),
        name="domain_detail"
    ),

]
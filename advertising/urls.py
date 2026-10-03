from django.urls import path

from . import views

urlpatterns = [
    path("", views.advertiser_dashboard, name="advertising_dashboard"),
    path("campaigns/create/", views.campaign_create, name="advertising_campaign_create"),
    path(
        "campaigns/<int:campaign_id>/edit/",
        views.campaign_edit,
        name="advertising_campaign_edit",
    ),
    path(
        "campaigns/<int:campaign_id>/<str:action>/",
        views.campaign_action,
        name="advertising_campaign_action",
    ),
    path(
        "campaigns/<int:campaign_id>/fund/",
        views.fund_campaign,
        name="advertising_fund_campaign",
    ),
    path(
        "paystack/callback/",
        views.paystack_callback,
        name="advertising_paystack_callback",
    ),
    path(
        "paystack/webhook/",
        views.paystack_webhook,
        name="advertising_paystack_webhook",
    ),
    path(
        "ads/<int:advertisement_id>/click/",
        views.advertisement_click,
        name="advertisement_click",
    ),
    path(
        "ads/<int:advertisement_id>/impression/",
        views.advertisement_impression,
        name="advertisement_impression",
    ),
    path(
        "ads/<int:advertisement_id>/impression/",
        views.advertisement_impression,
        name="advertisement_impression",
    ),
    path(
        "ads/<int:advertisement_id>/video-view/",
        views.advertisement_video_view,
        name="advertisement_video_view",
    ),
]

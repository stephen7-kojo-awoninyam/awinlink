from django.urls import path
from . import views

app_name = "marketplace_api"
urlpatterns = [
    path("markets/", views.Markets.as_view(), name="markets"),
    path("listings/", views.Listings.as_view(), name="listings"),
    path("listings/<int:pk>/", views.ListingDetail.as_view(), name="listing"),
    path("offers/", views.Offers.as_view(), name="offers"),
    path("deals/<int:pk>/", views.Deal.as_view(), name="deal"),
    path("deals/<int:pk>/messages/", views.Messages.as_view(), name="messages"),
]

from django.urls import path
from .views import market
from .booking_views import booking_page

app_name = "marketplace"
urlpatterns = [path("", market, name="home"), path('bookings/', booking_page, name='bookings')]

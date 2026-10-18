from django.urls import path
from .views import market

app_name = "marketplace"
urlpatterns = [path("", market, name="home")]

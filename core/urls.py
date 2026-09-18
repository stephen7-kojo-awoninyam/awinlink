from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    
    path("home_feed/",views.home_feed,name="home_feed"),
    
    path("explore/",views.explore,name="explore"),
]


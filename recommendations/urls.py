from django.urls import path

from . import views



urlpatterns = [
    path( "recommendations/<int:opportunity_id>/",views.recommendations,name="recommendations"),
]


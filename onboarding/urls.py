from django.urls import path
from . import views

urlpatterns = [

    path("",views.welcome,name="welcome"),
    path("role/",views.choose_role,name="choose_role"),
    path("talent/",views.talent_onboarding,name="talent_onboarding"),
    path("organization/",views.organization_onboarding,name="organization_onboarding"),
]
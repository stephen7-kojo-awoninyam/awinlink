from django.urls import path
from . import views

urlpatterns = [

    path( "verification/", views.verification_requests, name="verification_requests"),
    path("verification/approve/<int:request_id>/",views.approve_verification,name="approve_verification"),
    path("verification/reject/<int:request_id>/",views.reject_verification,name="reject_verification"),
    path("users/",views.user_management,name="user_management"),
    path("users/toggle/<int:user_id>/",views.toggle_user_status,name="toggle_user_status"),
    path("talents/",views.talent_management,name="talent_management"),
    path("talents/toggle/<int:talent_id>/",views.toggle_talent_status,name="toggle_talent_status"),
    path("organizations/",views.organization_management,name="organization_management"),
    path("organizations/toggle/<int:organization_id>/",views.toggle_organization_status,name="toggle_organization_status"),
    path("reports/",views.admin_reports,name="admin_reports"),
    path("",views.dashboard,name="dashboard")
]
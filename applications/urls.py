from django.urls import path
from . import views


urlpatterns = [

    path("apply/<int:opportunity_id>/",views.apply_opportunity,name="apply_opportunity"),
    path("accept/<int:application_id>/",views.accept_application,name="accept_application"),
    path("reject/<int:application_id>/",views.reject_application,name="reject_application"),
    path("review/<int:application_id>/",views.review_application,name="review_application"),


]
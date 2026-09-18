from django.urls import path
from . import views


urlpatterns = [
    path("create/", views.create_opportunity, name="create_opportunity"),
    path("",views.opportunity_list,name="opportunity_list"),
    path("apply/<int:opportunity_id>/",views.apply_opportunity,name="apply_opportunity"),
    path("recommendations/",views.recommended_opportunities,name="recommended_opportunities"),
    path("my-applications/",views.my_applications,name="my_applications"),
    path("<int:opportunity_id>/",views.opportunity_detail,name="opportunity_detail"),
]

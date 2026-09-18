from . import views

from django.urls import path


urlpatterns = [

    path(
        "pipeline/",
        views.recruitment_pipeline,
        name="recruitment_pipeline"
    ),


    path(

        "update/<int:stage_id>/<str:new_stage>/",

        views.update_pipeline_stage,

        name="update_pipeline_stage"

    ),

]
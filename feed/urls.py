from django.urls import path
# feed/urls.py

from django.urls import path

from . import views



urlpatterns = [


    path(

        "create/",

        views.create_post,

        name="create_post"

    ),
    
    path(

        "like/<int:post_id>/",

        views.like_post,

        name="like_post"

    ),
    path(

    "comment/<int:post_id>/",

    views.add_comment,

    name="add_comment"

   ),
    
    path(
        "save/<int:post_id>/",
        views.save_post,
        name="save_post"
    ),  
    
    path(
        "share/<int:post_id>/",
        views.share_post,
        name="share_post"
    ),   
   

]   


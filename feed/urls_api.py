from django.urls import path

from .api_views import (
PostCreateAPIView,
PostListAPIView,
PostDetailAPIView,
PostUpdateAPIView,
PostDeleteAPIView,
PostUnlikeAPIView,
PostLikesAPIView,
PostLikeAPIView,
PostCommentsAPIView, 
CommentDeleteAPIView,
)

app_name = "feed_api"

urlpatterns = [

# =====================================================
# POSTS
# =====================================================

path(
    "posts/",
    PostListAPIView.as_view(),
    name="post_list"
),

path(
    "posts/create/",
    PostCreateAPIView.as_view(),
    name="post_create"
),

path(
    "posts/<int:post_id>/",
    PostDetailAPIView.as_view(),
    name="post_detail"
),

path(
    "posts/<int:post_id>/update/",
    PostUpdateAPIView.as_view(),
    name="post_update"
),

path(
    "posts/<int:post_id>/delete/",
    PostDeleteAPIView.as_view(),
    name="post_delete"
),
# ===================================================== # 
# LIKES 
#  ===================================================== # 
 path( "posts/<int:post_id>/like/", PostLikeAPIView.as_view(), name="post_like" ), 
 path( "posts/<int:post_id>/unlike/", PostUnlikeAPIView.as_view(), name="post_unlike" ), 
 path( "posts/<int:post_id>/likes/", PostLikesAPIView.as_view(), name="post_likes" ),
# ===================================================== 
# # COMMENTS 
# # ===================================================== #
 path( "posts/<int:post_id>/comments/", PostCommentsAPIView.as_view(), name="post_comments" ), 
 path( "comments/<int:comment_id>/delete/", CommentDeleteAPIView.as_view(), name="comment_delete" ),

]

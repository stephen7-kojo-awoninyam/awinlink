from django.db.models import Q

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models import Post
from .serializers import PostSerializer,PostLike,PostLikeSerializer,Comment,CommentSerializer,SavedPost,SavedPostSerializer

from connections.models import Follow, OrganizationFollow

# ============================================================

# CREATE POST API

# ============================================================

class PostCreateAPIView(APIView):

    
    permission_classes = [IsAuthenticated]

    def post(self, request):

        serializer = PostSerializer(
            data=request.data,
            context={"request": request}
        )

        if not serializer.is_valid():

            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        post = serializer.save(
            author=request.user
        )

        serializer = PostSerializer(
            post,
            context={"request": request}
        )

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED
        )


# ============================================================

# FEED LIST API

# ============================================================

class PostListAPIView(APIView):

    
    permission_classes = [IsAuthenticated]

    def get(self, request):

        user = request.user

        # ----------------------------------------------------
        # POSTS THE USER CAN SEE
        # ----------------------------------------------------

        posts = Post.objects.filter(

            Q(visibility="PUBLIC")

            |

            Q(
                visibility="PRIVATE",
                author=user
            )

            |

            Q(
                visibility="FOLLOWERS",
                author=user
            )

        )

        # ----------------------------------------------------
        # FOLLOWED USERS
        # ----------------------------------------------------

        followed_users = Follow.objects.filter(
            follower=user
        ).values_list(
            "following_id",
            flat=True
        )

        posts = posts | Post.objects.filter(
            visibility="FOLLOWERS",
            author_id__in=followed_users
        )

        # ----------------------------------------------------
        # ORGANIZATION POSTS
        # ----------------------------------------------------

        followed_organizations = OrganizationFollow.objects.filter(
            user=user
        ).values_list(
            "organization_id",
            flat=True
        )

        posts = posts | Post.objects.filter(
            visibility="ORGANIZATIONS",
            organization_id__in=followed_organizations
        )

        # ----------------------------------------------------
        # USER'S OWN ORGANIZATION POSTS
        # ----------------------------------------------------

        try:

            organization = user.organization_profile

            posts = posts | Post.objects.filter(
                visibility="ORGANIZATIONS",
                organization=organization
            )

        except Exception:

            pass

        # ----------------------------------------------------
        # REMOVE DUPLICATES
        # ----------------------------------------------------

        posts = (
            posts
            .distinct()
            .select_related(
                "author",
                "talent",
                "organization",
                "event",
            )
            .order_by(
                "-created_at"
            )
        )

        serializer = PostSerializer(
            posts,
            many=True,
            context={"request": request}
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )


# ============================================================

# POST DETAIL API

# ============================================================

class PostDetailAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, post_id):

        try:

            post = (
                Post.objects
                .select_related(
                    "author",
                    "talent",
                    "organization",
                    "event",
                )
                .get(
                    id=post_id
                )
            )

        except Post.DoesNotExist:

            return Response(
                {
                    "detail": "Post not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ----------------------------------------------------
        # CHECK VISIBILITY
        # ----------------------------------------------------

        if not self.can_view_post(
            request.user,
            post
        ):

            return Response(
                {
                    "detail": (
                        "You do not have permission "
                        "to view this post."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = PostSerializer(
            post,
            context={"request": request}
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )

    # --------------------------------------------------------
    # VISIBILITY CHECK
    # --------------------------------------------------------

    def can_view_post(self, user, post):

        # Author can always see their own post

        if post.author == user:

            return True

        # Public

        if post.visibility == "PUBLIC":

            return True

        # Followers

        if post.visibility == "FOLLOWERS":

            return Follow.objects.filter(
                follower=user,
                following=post.author
            ).exists()

        # Organizations

        if post.visibility == "ORGANIZATIONS":

            if not post.organization:

                return False

            return OrganizationFollow.objects.filter(
                user=user,
                organization=post.organization
            ).exists()

        # Private

        return False


# ============================================================

# UPDATE POST API

# ============================================================

class PostUpdateAPIView(APIView):


    permission_classes = [IsAuthenticated]

    def patch(self, request, post_id):

        try:

            post = Post.objects.get(
                id=post_id
            )

        except Post.DoesNotExist:

            return Response(
                {
                    "detail": "Post not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ----------------------------------------------------
        # OWNERSHIP
        # ----------------------------------------------------

        if post.author != request.user:

            return Response(
                {
                    "detail": (
                        "You can only update "
                        "your own posts."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = PostSerializer(
            post,
            data=request.data,
            partial=True,
            context={"request": request}
        )

        if not serializer.is_valid():

            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer.save()

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )


# ============================================================

# DELETE POST API

# ============================================================

class PostDeleteAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def delete(self, request, post_id):

        try:

            post = Post.objects.get(
                id=post_id
            )

        except Post.DoesNotExist:

            return Response(
                {
                    "detail": "Post not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ----------------------------------------------------
        # OWNERSHIP
        # ----------------------------------------------------

        if post.author != request.user:

            return Response(
                {
                    "detail": (
                        "You can only delete "
                        "your own posts."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        post.delete()

        return Response(
            {
                "detail": "Post deleted successfully."
            },
            status=status.HTTP_200_OK
        )



# ============================================================

# LIKE POST API

# ============================================================

class PostLikeAPIView(APIView):

    
    permission_classes = [IsAuthenticated]

    def post(self, request, post_id):

        try:

            post = Post.objects.get(
                id=post_id
            )

        except Post.DoesNotExist:

            return Response(
                {
                    "detail": "Post not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ----------------------------------------------------
        # CHECK EXISTING LIKE
        # ----------------------------------------------------

        if PostLike.objects.filter(
            user=request.user,
            post=post
        ).exists():

            return Response(
                {
                    "detail": "You already liked this post."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ----------------------------------------------------
        # CREATE LIKE
        # ----------------------------------------------------

        like = PostLike.objects.create(
            user=request.user,
            post=post
        )

        # ----------------------------------------------------
        # SERIALIZE
        # ----------------------------------------------------

        serializer = PostLikeSerializer(
            like,
            context={"request": request}
        )

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED
        )


# ============================================================

# UNLIKE POST API

# ============================================================

class PostUnlikeAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def delete(self, request, post_id):

        try:

            like = PostLike.objects.get(
                user=request.user,
                post_id=post_id
            )

        except PostLike.DoesNotExist:

            return Response(
                {
                    "detail": "You have not liked this post."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        like.delete()

        return Response(
            {
                "detail": "Post unliked successfully."
            },
            status=status.HTTP_200_OK
        )


# ============================================================

# POST LIKES API

# ============================================================

class PostLikesAPIView(APIView):


    permission_classes = [IsAuthenticated]

    def get(self, request, post_id):

        try:

            post = Post.objects.get(
                id=post_id
            )

        except Post.DoesNotExist:

            return Response(
                {
                    "detail": "Post not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        likes = (
            PostLike.objects
            .filter(
                post=post
            )
            .select_related(
                "user"
            )
            .order_by(
                "-created_at"
            )
        )

        serializer = PostLikeSerializer(
            likes,
            many=True,
            context={"request": request}
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
        
        
        
# ============================================================

# POST COMMENTS API

# ============================================================

class PostCommentsAPIView(APIView):


    permission_classes = [IsAuthenticated]

    def get(self, request, post_id):

        try:

            post = Post.objects.get(
                id=post_id
            )

        except Post.DoesNotExist:

            return Response(
                {
                    "detail": "Post not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        comments = (
            Comment.objects
            .filter(
                post=post
            )
            .select_related(
                "user"
            )
            .order_by(
                "-created_at"
            )
        )

        serializer = CommentSerializer(
            comments,
            many=True,
            context={"request": request}
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )

    def post(self, request, post_id):

        try:

            post = Post.objects.get(
                id=post_id
            )

        except Post.DoesNotExist:

            return Response(
                {
                    "detail": "Post not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        text = request.data.get(
            "text",
            ""
        ).strip()

        if not text:

            return Response(
                {
                    "detail": "Comment text is required."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        comment = Comment.objects.create(
            user=request.user,
            post=post,
            text=text
        )

        serializer = CommentSerializer(
            comment,
            context={"request": request}
        )

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED
        )


# ============================================================

# COMMENT DETAIL / DELETE API

# ============================================================

class CommentDeleteAPIView(APIView):


    permission_classes = [IsAuthenticated]

    def delete(self, request, comment_id):

        try:

            comment = (
                Comment.objects
                .select_related(
                    "user",
                    "post"
                )
                .get(
                    id=comment_id
                )
            )

        except Comment.DoesNotExist:

            return Response(
                {
                    "detail": "Comment not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ----------------------------------------------------
        # ONLY COMMENT AUTHOR CAN DELETE
        # ----------------------------------------------------

        if comment.user != request.user:

            return Response(
                {
                    "detail": (
                        "You can only delete "
                        "your own comments."
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        comment.delete()

        return Response(
            {
                "detail": "Comment deleted successfully."
            },
            status=status.HTTP_200_OK
        )

        
# ============================================================

# SAVE POST API

# ============================================================

class SavePostAPIView(APIView):

    
    permission_classes = [IsAuthenticated]

    def post(self, request, post_id):

        try:

            post = Post.objects.get(
                id=post_id
            )

        except Post.DoesNotExist:

            return Response(
                {
                    "detail": "Post not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ----------------------------------------------------
        # CHECK EXISTING SAVE
        # ----------------------------------------------------

        if SavedPost.objects.filter(
            user=request.user,
            post=post
        ).exists():

            return Response(
                {
                    "detail": "You already saved this post."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ----------------------------------------------------
        # CREATE SAVE
        # ----------------------------------------------------

        saved_post = SavedPost.objects.create(
            user=request.user,
            post=post
        )

        serializer = SavedPostSerializer(
            saved_post,
            context={"request": request}
        )

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED
        )


# ============================================================

# UNSAVE POST API

# ============================================================

class UnsavePostAPIView(APIView):

    
    permission_classes = [IsAuthenticated]

    def delete(self, request, post_id):

        try:

            saved_post = SavedPost.objects.get(
                user=request.user,
                post_id=post_id
            )

        except SavedPost.DoesNotExist:

            return Response(
                {
                    "detail": "You have not saved this post."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        saved_post.delete()

        return Response(
            {
                "detail": "Post removed from saved posts."
            },
            status=status.HTTP_200_OK
        )


# ============================================================

# MY SAVED POSTS API

# ============================================================

class MySavedPostsAPIView(APIView):

    
    permission_classes = [IsAuthenticated]

    def get(self, request):

        saved_posts = (
            SavedPost.objects
            .filter(
                user=request.user
            )
            .select_related(
                "post",
                "post__author",
                "post__talent",
                "post__organization",
                "post__event",
            )
            .order_by(
                "-created_at"
            )
        )

        serializer = SavedPostSerializer(
            saved_posts,
            many=True,
            context={"request": request}
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )




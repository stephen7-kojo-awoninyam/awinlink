from rest_framework import serializers

from .models import (
Post,
PostLike,
Comment,
SavedPost,
SharedPost,
)

# ============================================================

# POST SERIALIZER

# ============================================================

class PostSerializer(serializers.ModelSerializer):

    author_name = serializers.SerializerMethodField()

    author_username = serializers.SerializerMethodField()

    author_profile_picture = serializers.SerializerMethodField()

    talent_name = serializers.SerializerMethodField()

    organization_name = serializers.SerializerMethodField()

    event_title = serializers.SerializerMethodField()

    likes_count = serializers.SerializerMethodField()

    comments_count = serializers.SerializerMethodField()

    saves_count = serializers.SerializerMethodField()

    shares_count = serializers.SerializerMethodField()

    is_liked = serializers.SerializerMethodField()

    is_saved = serializers.SerializerMethodField()

    class Meta:

        model = Post

        fields = [
            "id",

            "author",
            "author_name",
            "author_username",
            "author_profile_picture",

            "talent",
            "talent_name",

            "organization",
            "organization_name",

            "event",
            "event_title",

            "caption",

            "image",
            "video",

            "post_type",
            "visibility",

            "location",

            "views",

            "likes_count",
            "comments_count",
            "saves_count",
            "shares_count",

            "is_liked",
            "is_saved",

            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "author",

            "views",

            "likes_count",
            "comments_count",
            "saves_count",
            "shares_count",

            "is_liked",
            "is_saved",

            "created_at",
            "updated_at",
        ]

    # --------------------------------------------------------
    # AUTHOR
    # --------------------------------------------------------

    def get_author_name(self, obj):

        return (
            obj.author.get_full_name()
            or obj.author.username
        )

    def get_author_username(self, obj):

        return obj.author.username

    def get_author_profile_picture(self, obj):

        if obj.author.profile_picture:

            request = self.context.get("request")

            if request:

                return request.build_absolute_uri(
                    obj.author.profile_picture.url
                )

            return obj.author.profile_picture.url

        return None

    # --------------------------------------------------------
    # TALENT
    # --------------------------------------------------------

    def get_talent_name(self, obj):

        if obj.talent:

            return (
                obj.talent.user.get_full_name()
                or obj.talent.user.username
            )

        return None

    # --------------------------------------------------------
    # ORGANIZATION
    # --------------------------------------------------------

    def get_organization_name(self, obj):

        if obj.organization:

            return obj.organization.name

        return None

    # --------------------------------------------------------
    # EVENT
    # --------------------------------------------------------

    def get_event_title(self, obj):

        if obj.event:

            return obj.event.title

        return None

    # --------------------------------------------------------
    # COUNTS
    # --------------------------------------------------------

    def get_likes_count(self, obj):

        return obj.likes.count()

    def get_comments_count(self, obj):

        return obj.comments.count()

    def get_saves_count(self, obj):

        return obj.saves.count()

    def get_shares_count(self, obj):

        return obj.shares.count()

# --------------------------------------------------------
# CURRENT USER STATE
# --------------------------------------------------------

def get_is_liked(self, obj):

    request = self.context.get("request")

    if not request or not request.user.is_authenticated:

        return False

    return PostLike.objects.filter(
        post=obj,
        user=request.user
    ).exists()

def get_is_saved(self, obj):

    request = self.context.get("request")

    if not request or not request.user.is_authenticated:

        return False

    return SavedPost.objects.filter(
        post=obj,
        user=request.user
    ).exists()


# ============================================================

# POST LIKE SERIALIZER

# ============================================================

class PostLikeSerializer(serializers.ModelSerializer):


    user_name = serializers.SerializerMethodField()

    class Meta:

        model = PostLike

        fields = [
            "id",
            "user",
            "user_name",
            "post",
            "created_at",
        ]

        read_only_fields = [
            "user",
            "created_at",
        ]

    def get_user_name(self, obj):

        return (
            obj.user.get_full_name()
            or obj.user.username
        )


# ============================================================

# COMMENT SERIALIZER

# ============================================================

class CommentSerializer(serializers.ModelSerializer):


    user_name = serializers.SerializerMethodField()

    user_username = serializers.SerializerMethodField()

    class Meta:

        model = Comment

        fields = [
            "id",
            "user",
            "user_name",
            "user_username",
            "post",
            "text",
            "created_at",
        ]

    read_only_fields = [
        "user",
        "created_at",
    ]

    def get_user_name(self, obj):

        return (
            obj.user.get_full_name()
            or obj.user.username
        )

    def get_user_username(self, obj):

        return obj.user.username

# ============================================================

# SAVED POST SERIALIZER

# ============================================================

class SavedPostSerializer(serializers.ModelSerializer):


    class Meta:

        model = SavedPost

        fields = [
            "id",
            "user",
            "post",
            "created_at",
        ]

        read_only_fields = [
            "user",
            "created_at",
        ]


# ============================================================

# SHARED POST SERIALIZER

# ============================================================

class SharedPostSerializer(serializers.ModelSerializer):

    user_name = serializers.SerializerMethodField()

    original_post = serializers.SerializerMethodField()

    class Meta:

        model = SharedPost

        fields = [
            "id",
            "user",
            "user_name",
            "post",
            "original_post",
            "caption",
            "created_at",
        ]

        read_only_fields = [
            "user",
            "created_at",
        ]

    def get_user_name(self, obj):

        return (
            obj.user.get_full_name()
            or obj.user.username
        )

    def get_original_post(self, obj):

        return PostSerializer(
            obj.post,
            context=self.context
        ).data


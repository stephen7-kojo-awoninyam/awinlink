from django.contrib import admin

# Register your models here.

from .models import (
    Post,
    PostLike,
    Comment
)



@admin.register(Post)
class PostAdmin(admin.ModelAdmin):


    list_display = (

        "author",
        "post_type",
        "views",
        "created_at",

    )


    list_filter = (

        "post_type",

    )


    search_fields = (

        "author__username",

        "caption",

    )




@admin.register(PostLike)
class PostLikeAdmin(admin.ModelAdmin):

    list_display = (

        "user",
        "post",
        "created_at",

    )




@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):

    list_display = (

        "user",
        "post",
        "created_at",

    )
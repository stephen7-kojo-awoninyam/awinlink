from django.contrib import admin
from .models import Follow
from .models import Connection
# Register your models here.

@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):


    list_display = (

        "follower",

        "following",

        "created_at",

    )


    search_fields = (

        "follower__username",

        "following__username",

    )
    
    
    



@admin.register(Connection)
class ConnectionAdmin(admin.ModelAdmin):

    list_display = (
        "sender",
        "receiver",
        "status",
        "created_at",
        "updated_at",
    )

    list_filter = (
        "status",
        "created_at",
    )

    search_fields = (
        "sender__username",
        "receiver__username",
    )    
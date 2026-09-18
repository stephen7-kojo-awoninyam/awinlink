from django.contrib import admin
from .models import PortfolioItem
# Register your models here.
from django.contrib import admin


@admin.register(PortfolioItem)
class PortfolioItemAdmin(admin.ModelAdmin):


    list_display = (

        "title",

        "talent",

        "item_type",

        "created_at",

    )


    list_filter = (

        "item_type",

        "created_at",

    )


    search_fields = (

        "title",

        "description",

        "talent__user__first_name",

        "talent__user__last_name",

    )


    autocomplete_fields = (

        "talent",

    )
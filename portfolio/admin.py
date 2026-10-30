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

    def save_model(self, request, obj, form, change):
        if change:
            from media_erasure.services import save_instance_with_media_retention
            save_instance_with_media_retention(obj,
                lambda: super(PortfolioItemAdmin, self).save_model(request, obj, form, change),
                requested_by_id=request.user.pk)
            return
        super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        from media_erasure.services import delete_instance_with_retention
        delete_instance_with_retention(obj, requested_by_id=request.user.pk)

    def delete_queryset(self, request, queryset):
        from django.db import transaction
        from media_erasure.services import delete_instance_with_retention
        with transaction.atomic():
            for obj in queryset.select_for_update().order_by('pk'):
                delete_instance_with_retention(obj, requested_by_id=request.user.pk)

from django.contrib import admin

from .models import MediaErasureJob, MediaLegalHold


@admin.register(MediaErasureJob)
class MediaErasureJobAdmin(admin.ModelAdmin):
    list_display = ('storage_name', 'source_model', 'source_pk', 'source_field', 'retain_until', 'state')
    list_filter = ('state', 'storage_kind')
    search_fields = ('storage_name', 'source_model', 'source_pk', 'source_field')
    readonly_fields = tuple(field.name for field in MediaErasureJob._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MediaLegalHold)
class MediaLegalHoldAdmin(admin.ModelAdmin):
    list_display = ('storage_name', 'provider_asset_id', 'held', 'placed_at', 'released_at')
    list_filter = ('held', 'placed_at')
    search_fields = ('storage_name', 'provider_asset_id', 'reason')
    readonly_fields = ('placed_by_id', 'placed_at', 'released_by_id', 'released_at')

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            fields.extend(('storage_name', 'provider_asset_id', 'reason'))
            if not obj.held:
                fields.append('held')
        return tuple(fields)

    def has_add_permission(self, request):
        return bool(request.user.is_superuser)

    def has_change_permission(self, request, obj=None):
        return bool(request.user.is_superuser)

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        from .services import save_legal_hold
        save_legal_hold(obj, actor_id=request.user.pk)

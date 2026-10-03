from django.contrib import admin

from .models import Advertisement, AdvertisementEvent, Campaign, CampaignPayment


class AdvertisementInline(admin.StackedInline):
    model = Advertisement
    extra = 0


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "organization",
        "status",
        "billing_model",
        "total_budget",
        "currency",
        "start_date",
        "end_date",
        "created_at",
    )
    list_filter = ("status", "billing_model", "currency")
    search_fields = ("name", "organization__name")
    readonly_fields = ("created_at", "updated_at", "funded_amount", "spent_amount")
    inlines = (AdvertisementInline,)
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "organization",
                    "name",
                    "status",
                    "review_note",
                    "start_date",
                    "end_date",
                )
            },
        ),
        (
            "Budget and billing",
            {
                "fields": (
                    "billing_model",
                    "currency",
                    "total_budget",
                    "daily_budget",
                    "cost_per_thousand_impressions",
                    "cost_per_click",
                    "funded_amount",
                    "spent_amount",
                )
            },
        ),
        (
            "Targeting and frequency",
            {
                "fields": (
                    "target_categories",
                    "domains",
                    "sports",
                    "skills",
                    "frequency_cap",
                    "frequency_window_hours",
                    "priority",
                )
            },
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(Advertisement)
class AdvertisementAdmin(admin.ModelAdmin):
    list_display = ("title", "campaign", "cta_label", "created_at")
    search_fields = ("title", "campaign__name", "campaign__organization__name")
    readonly_fields = ("created_at", "updated_at")


@admin.register(CampaignPayment)
class CampaignPaymentAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "campaign",
        "amount",
        "currency",
        "status",
        "created_at",
        "paid_at",
    )
    list_filter = ("status", "currency")
    search_fields = ("reference", "campaign__name", "campaign__organization__name")
    readonly_fields = (
        "campaign",
        "reference",
        "amount",
        "currency",
        "authorization_url",
        "status",
        "paid_at",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AdvertisementEvent)
class AdvertisementEventAdmin(admin.ModelAdmin):
    list_display = ("advertisement", "user", "event_type", "created_at")
    list_filter = ("event_type", "created_at")
    search_fields = ("advertisement__title", "user__username")
    readonly_fields = ("advertisement", "user", "event_type", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

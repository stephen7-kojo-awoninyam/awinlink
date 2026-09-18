from django.contrib import admin

from .models import (
    OrganizationCategory,
    OrganizationDomain,
    Organization,
    SportsOrganizationProfile
)



# =====================================
# ORGANIZATION CATEGORY ADMIN
# =====================================

@admin.register(OrganizationCategory)
class OrganizationCategoryAdmin(admin.ModelAdmin):

    list_display = (
        "name",
    )

    search_fields = (
        "name",
    )



# =====================================
# ORGANIZATION DOMAIN ADMIN
# =====================================

@admin.register(OrganizationDomain)
class OrganizationDomainAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "category",
    )


    search_fields = (
        "name",
        "category__name",
    )


    list_filter = (
        "category",
    )



# =====================================
# ORGANIZATION ADMIN
# =====================================

@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):


    list_display = (
        "name",
        "category",
        "domain",
        "country",
        "level",
        "organization_size",
        "official",
        "claimed",
        "verified",
        "status",
    )


    search_fields = (
        "name",
        "country",
        "city",
        "email",
        "domain__name",
        "category__name",
    )


    list_filter = (
        "status",
        "verified",
        "official",
        "claimed",
        "level",
        "organization_size",
        "category",
        "domain",
        "country",
    )


    readonly_fields = (
        "created_at",
        "claimed_at",
    )


    fieldsets = (

        (
            "Basic Information",
            {
                "fields": (
                    "user",
                    "name",
                    "category",
                    "domain",
                    "description",
                    "logo",
                )
            }
        ),


        (
            "Location",
            {
                "fields": (
                    "country",
                    "city",
                    "headquarters",
                )
            }
        ),


        (
            "Contact",
            {
                "fields": (
                    "website",
                    "email",
                    "phone",
                )
            }
        ),


        (
            "Organization Profile",
            {
                "fields": (
                    "founded_year",
                    "organization_size",
                    "level",
                )
            }
        ),


        (
            "Verification",
            {
                "fields": (
                    "official",
                    "verified",
                    "claimed",
                    "claimed_at",
                    "status",
                )
            }
        ),


        (
            "System Information",
            {
                "fields": (
                    "created_at",
                )
            }
        ),

    )



# =====================================
# SPORTS PROFILE ADMIN
# =====================================

@admin.register(SportsOrganizationProfile)
class SportsOrganizationProfileAdmin(admin.ModelAdmin):


    list_display = (
        "organization",
        "sport",
        "league",
        "level",
        "nickname",
    )


    search_fields = (
        "organization__name",
        "league",
        "nickname",
    )


    list_filter = (
        "level",
        "sport",
    )


    fieldsets = (

        (
            "Organization",
            {
                "fields": (
                    "organization",
                    "sport",
                )
            }
        ),


        (
            "Sports Information",
            {
                "fields": (
                    "league",
                    "level",
                    "nickname",
                    "colors",
                    "stadium",
                    "founded",
                    "website",
                )
            }
        ),

    )
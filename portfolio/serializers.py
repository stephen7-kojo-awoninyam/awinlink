
from rest_framework import serializers

from .models import PortfolioItem


# ============================================================
# PORTFOLIO ITEM
# ============================================================

class PortfolioItemSerializer(serializers.ModelSerializer):

    talent_id = serializers.IntegerField(
        source="talent.id",
        read_only=True
    )

    talent_name = serializers.CharField(
        source="talent.user.get_full_name",
        read_only=True
    )

    class Meta:

        model = PortfolioItem

        fields = [
            "id",
            "talent_id",
            "talent_name",
            "title",
            "description",
            "item_type",
            "image",
            "file",
            "link",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "talent_id",
            "talent_name",
            "created_at",
        ]



from rest_framework import serializers
from collections.abc import Mapping

from .models import PortfolioItem
from .permissions import OWNERSHIP_FIELDS


# ============================================================
# PORTFOLIO ITEM
# ============================================================

class PortfolioItemSerializer(serializers.ModelSerializer):

    def to_internal_value(self, data):
        if isinstance(data, Mapping) and OWNERSHIP_FIELDS.intersection(data):
            raise serializers.ValidationError({'non_field_errors': ['Portfolio ownership cannot be changed here.']})
        return super().to_internal_value(data)

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


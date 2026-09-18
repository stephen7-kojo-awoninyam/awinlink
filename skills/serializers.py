from rest_framework import serializers

from .models import (
    SkillCategory,
    Skill,
)


# ============================================================
# SKILL CATEGORY
# ============================================================

class SkillCategorySerializer(serializers.ModelSerializer):

    class Meta:

        model = SkillCategory

        fields = [
            "id",
            "name",
        ]

        read_only_fields = [
            "id",
        ]


# ============================================================
# SKILL
# ============================================================

class SkillSerializer(serializers.ModelSerializer):

    category_name = serializers.CharField(
        source="category.name",
        read_only=True
    )

    class Meta:

        model = Skill

        fields = [
            "id",
            "name",
            "category",
            "category_name",
        ]

        read_only_fields = [
            "id",
            "category_name",
        ]


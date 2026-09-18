from rest_framework import serializers

from .models import TalentDomain


class TalentDomainSerializer(serializers.ModelSerializer):

    class Meta:

        model = TalentDomain

        fields = [
            "id",
            "name",
            "description",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "created_at",
        ]
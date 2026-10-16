from rest_framework import serializers

from recommendations.models import RecommendationFeedback


class StrictInputSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({
                    field: "Unexpected field." for field in sorted(unknown)
                })
            if "kind" in data:
                data = {**data, "kind": str(data["kind"]).upper()}
        return super().to_internal_value(data)


class InterestPreferenceInputSerializer(StrictInputSerializer):
    inferred_interests_enabled = serializers.BooleanField(required=True)


class RecommendationFeedbackItemSerializer(StrictInputSerializer):
    kind = serializers.ChoiceField(choices=RecommendationFeedback.ItemKind.choices)
    item_id = serializers.IntegerField(min_value=1)


class RecommendationFeedbackBatchSerializer(StrictInputSerializer):
    items = RecommendationFeedbackItemSerializer(many=True, required=False, allow_empty=False)
    kind = serializers.ChoiceField(choices=RecommendationFeedback.ItemKind.choices, required=False)
    item_id = serializers.IntegerField(min_value=1, required=False)

    def validate(self, attrs):
        super().validate(attrs)
        has_batch = "items" in attrs
        has_single = "kind" in attrs or "item_id" in attrs
        if has_batch == has_single:
            raise serializers.ValidationError("Provide either items or one kind and item_id.")
        if has_single and not ("kind" in attrs and "item_id" in attrs):
            raise serializers.ValidationError("Both kind and item_id are required.")
        entries = attrs.get("items", [])
        if has_single:
            entries = [{"kind": attrs["kind"], "item_id": attrs["item_id"]}]
        if len(entries) > 100:
            raise serializers.ValidationError({"items": "At most 100 items may be submitted."})
        attrs["entries"] = entries
        return attrs

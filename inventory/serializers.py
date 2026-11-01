
from rest_framework import serializers

from catalog.models import Product
from .models import InventoryMovement


class InventoryMovementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(
        source="product.name",
        read_only=True,
    )
    product_sku = serializers.CharField(
        source="product.sku",
        read_only=True,
    )
    username = serializers.CharField(
        source="user.username",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = InventoryMovement
        fields = [
            "id",
            "product",
            "product_name",
            "product_sku",
            "movement_type",
            "quantity",
            "reference",
            "note",
            "user",
            "username",
            "created_at",
        ]
        read_only_fields = fields


class StockMovementRequestSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(),
    )
    quantity = serializers.IntegerField(min_value=1)
    reference = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        default="",
    )
    note = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )

    def validate_product(self, product):
        if not product.is_active:
            raise serializers.ValidationError(
                "Cannot change stock for an inactive product."
            )
        return product

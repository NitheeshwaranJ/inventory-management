
from rest_framework import serializers
from .models import Product


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(
        source="category.name",
        read_only=True,
    )
    supplier_name = serializers.CharField(
        source="supplier.name",
        read_only=True,
    )

    class Meta:
        model = Product
        fields = [
            "id",
            "sku",
            "name",
            "description",
            "category",
            "category_name",
            "supplier",
            "supplier_name",
            "cost_price",
            "selling_price",
            "stock",
            "low_stock_threshold",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "stock",
            "created_at",
            "updated_at",
        ]

    def validate_sku(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "SKU cannot be empty."
            )

        queryset = Product.objects.filter(sku__iexact=value)

        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.exists():
            raise serializers.ValidationError(
                "A product with this SKU already exists."
            )

        return value

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError(
                "Product name cannot be empty."
            )
        return value.strip()

    def validate(self, attrs):
        cost_price = attrs.get(
            "cost_price",
            getattr(self.instance, "cost_price", None),
        )
        selling_price = attrs.get(
            "selling_price",
            getattr(self.instance, "selling_price", None),
        )

        if cost_price is not None and cost_price < 0:
            raise serializers.ValidationError({
                "cost_price": "Cost price cannot be negative."
            })

        if selling_price is not None and selling_price < 0:
            raise serializers.ValidationError({
                "selling_price": "Selling price cannot be negative."
            })

        return attrs

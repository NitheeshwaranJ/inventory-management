
from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, Sum

from catalog.models import Product


def get_inventory_valuation():
    """
    Return the total cost value of stock for active products,
    plus a per-product breakdown.
    """
    products = Product.objects.filter(
        is_active=True,
        stock__gt=0,
    ).select_related("category").order_by("name")

    value_expression = ExpressionWrapper(
        F("stock") * F("cost_price"),
        output_field=DecimalField(max_digits=20, decimal_places=2),
    )

    total_value = products.aggregate(
        total=Sum(value_expression)
    )["total"] or Decimal("0.00")

    breakdown = [
        {
            "product_id": product.id,
            "sku": product.sku,
            "name": product.name,
            "stock": product.stock,
            "cost_price": product.cost_price,
            "inventory_value": product.stock * product.cost_price,
        }
        for product in products
    ]

    return {
        "total_inventory_value": total_value,
        "product_count": len(breakdown),
        "products": breakdown,
    }

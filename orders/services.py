
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from catalog.models import Product
from inventory.models import InventoryMovement
from .models import Order, OrderItem


@transaction.atomic
def create_order(
    items,
    customer_name="",
    customer_email="",
    user=None,
):
    """
    Create an order, save purchase-time prices, deduct stock,
    and record stock movements in one database transaction.

    Expected items:
    [
        {"product_id": 1, "quantity": 2},
        {"product_id": 3, "quantity": 1},
    ]
    """

    # 1. Validate the overall request.
    if not isinstance(items, list) or not items:
        raise ValidationError(
            {"items": "An order must contain at least one item."}
        )

    seen_product_ids = set()

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValidationError(
                {"items": f"Item {index + 1} must be an object."}
            )

        product_id = item.get("product_id")
        quantity = item.get("quantity")

        if (
            isinstance(product_id, bool)
            or not isinstance(product_id, int)
            or product_id <= 0
        ):
            raise ValidationError({
                "items": f"Item {index + 1} has an invalid product ID."
            })

        if (
            isinstance(quantity, bool)
            or not isinstance(quantity, int)
            or quantity <= 0
        ):
            raise ValidationError({
                "items": f"Item {index + 1} quantity must be a positive integer."
            })

        if product_id in seen_product_ids:
            raise ValidationError({
                "items": (
                    "A product can appear only once in an order. "
                    "Combine its quantities into one item."
                )
            })

        seen_product_ids.add(product_id)

    # 2. Lock products in consistent ID order.
    # Row-level locking works on databases such as PostgreSQL.
    products = Product.objects.select_for_update().filter(
        id__in=seen_product_ids
    ).order_by("id")

    product_by_id = {product.id: product for product in products}

    # 3. Validate every product and stock balance before changing anything.
    for item in items:
        product_id = item["product_id"]
        quantity = item["quantity"]

        product = product_by_id.get(product_id)

        if product is None:
            raise ValidationError({
                "items": f"Product {product_id} does not exist."
            })

        if not product.is_active:
            raise ValidationError({
                "items": f"Product {product.sku} is inactive."
            })

        if product.stock < quantity:
            raise ValidationError({
                "items": (
                    f"Insufficient stock for {product.sku}. "
                    f"Available: {product.stock}; requested: {quantity}."
                )
            })

    # 4. Create the order inside the transaction.
    order = Order.objects.create(
        customer_name=customer_name,
        customer_email=customer_email,
        created_by=user,
        total_amount=Decimal("0.00"),
    )

    total = Decimal("0.00")

    # 5. Save purchase-time prices and deduct stock.
    for item in items:
        product = product_by_id[item["product_id"]]
        quantity = item["quantity"]
        purchase_price = product.selling_price

        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=quantity,
            unit_price=purchase_price,
        )

        # Record stock deduction and movement history.
        # The service is atomic too; its transaction nests safely here.
        from inventory.services import stock_out

        stock_out(
            product_id=product.id,
            quantity=quantity,
            user=user,
            reference=f"ORDER-{order.id}",
            note=f"Stock issued for order #{order.id}",
        )

        total += purchase_price * quantity

    # 6. Store the server-calculated total.
    order.total_amount = total
    order.save(update_fields=["total_amount", "updated_at"])

    return order

@transaction.atomic
def cancel_order(order_id, user=None):
    """
    Cancel a placed order and restore its stock exactly once.

    Stock restoration, return movements, and the order status
    change are committed together or rolled back together.
    """

    try:
      order = Order.objects.select_for_update().get(pk=order_id)
    except Order.DoesNotExist:
      raise ValidationError({"order": "Order does not exist."})

# Authorization must be checked inside the service as well.
    if user is None:
      raise ValidationError({
        "detail": "An authenticated user is required to cancel an order."
    })

    if not (user.is_staff or user.is_superuser):
      if order.created_by_id != user.id:
        raise ValidationError({
            "detail": "You do not have permission to cancel this order."
        })

    # Idempotency: repeated cancellation must not restore stock again.
    if order.status == Order.Status.CANCELLED:
        return order

    if order.status != Order.Status.PLACED:
        raise ValidationError({
            "order": f"Cannot cancel an order with status {order.status}."
        })

    order_items = list(
        order.items.order_by("product_id").values("product_id", "quantity")
    )

    product_ids = [item["product_id"] for item in order_items]

    # Lock product rows in a consistent order.
    products = Product.objects.select_for_update().filter(
        id__in=product_ids
    ).order_by("id")

    product_by_id = {product.id: product for product in products}

    if len(product_by_id) != len(set(product_ids)):
        raise ValidationError({
            "order": "A product associated with this order no longer exists."
        })

    movement_user = user if user is not None else order.created_by

    # Restore each item's quantity and record the audit trail.
    for item in order_items:
        product = product_by_id[item["product_id"]]
        quantity = item["quantity"]

        product.stock += quantity
        product.save(update_fields=["stock", "updated_at"])

        InventoryMovement.objects.create(
            product=product,
            movement_type=InventoryMovement.MovementType.RETURN,
            quantity=quantity,
            reference=f"ORDER-{order.id}-CANCEL",
            note=f"Stock restored for cancelled order #{order.id}",
            user=movement_user,
        )

    order.status = Order.Status.CANCELLED
    order.save(update_fields=["status", "updated_at"])

    return order
